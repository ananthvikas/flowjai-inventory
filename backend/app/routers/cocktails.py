"""
routers/cocktails.py

Two-phase cocktail workflow:
  1. POST /cocktails/preview  - dry run, returns warnings, no DB changes
  2. POST /cocktails/         - commits mixing, deducts stock
  3. POST /cocktails/{id}/use - logs tests against cocktail, decrements remaining_tests
  4. GET  /cocktails/         - list active cocktails
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_technologist_or_admin
from app.database import get_session
from app.models import (
    Antibody, AlertRule, Cocktail, CocktailUsageLog,
    Panel, PanelComponent, User,
)
from app.services.consumption import get_total_stock_ul
from app.services.cocktails import prepare, prepared_by_name
from app.services.forecast import forecast_antibody

router = APIRouter(prefix="/api/cocktails", tags=["cocktails"])

DEFAULT_ALERT_THRESHOLD_DAYS = 42


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CocktailPreviewRequest(BaseModel):
    panel_id: int
    total_tests: int


class AffectedPanel(BaseModel):
    panel_id: int
    panel_name: str
    test_code: str


class ComponentWarning(BaseModel):
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    needed_ul: float
    current_stock_ul: float
    remaining_after_ul: float
    days_remaining_after: Optional[float]
    alert_threshold_days: int
    severity: str
    affected_panels: List[AffectedPanel]


class ComponentPreview(BaseModel):
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    vendor: Optional[str]
    volume_per_tube_ul: float
    tubes_per_test: int
    ul_per_test: float
    total_ul_needed: float
    current_stock_ul: float
    remaining_after_ul: float
    has_warning: bool


class CocktailPreviewResponse(BaseModel):
    panel_id: int
    panel_name: str
    total_tests: int
    components: List[ComponentPreview]
    warnings: List[ComponentWarning]
    can_proceed: bool


class CocktailCreate(BaseModel):
    panel_id: int
    total_tests: int
    expiry_date: Optional[date] = None
    lot_notes: Optional[str] = None
    prepared_by_staff_id: Optional[int] = None


class CocktailUsageCreate(BaseModel):
    test_date: date
    count: int
    notes: Optional[str] = None


class CocktailRead(BaseModel):
    id: int
    cocktail_code: Optional[str] = None
    panel_id: int
    panel_name: str
    prepared_by: int
    prepared_by_username: str
    prepared_by_staff_id: Optional[int] = None
    prepared_by_name: Optional[str] = None     # staff name, else login username
    prepared_at: Optional[str] = None          # timestamp the prep was recorded
    prepared_date: str
    total_tests: int
    remaining_tests: int
    reserved_tests: int
    available_tests: int
    expiry_date: Optional[str]
    lot_notes: Optional[str]
    active: bool
    pct_remaining: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_threshold(antibody_id: int, session: Session) -> int:
    rule = session.exec(
        select(AlertRule).where(AlertRule.antibody_id == antibody_id)
    ).first()
    return rule.alert_threshold_days if rule else DEFAULT_ALERT_THRESHOLD_DAYS


def _other_panels_using(antibody_id: int, exclude_panel_id: int, session: Session) -> List[AffectedPanel]:
    comps = session.exec(
        select(PanelComponent)
        .where(PanelComponent.antibody_id == antibody_id)
        .where(PanelComponent.panel_id != exclude_panel_id)
    ).all()
    result = []
    seen = set()
    for c in comps:
        if c.panel_id in seen:
            continue
        seen.add(c.panel_id)
        panel = session.get(Panel, c.panel_id)
        if panel and panel.active:
            result.append(AffectedPanel(
                panel_id=panel.id,
                panel_name=panel.name,
                test_code=panel.test_code,
            ))
    return result


def _build_preview(panel, components, total_tests, session):
    preview_components = []
    warnings = []
    can_proceed = True

    for comp in components:
        ab = session.get(Antibody, comp.antibody_id)
        if not ab:
            continue

        fluor = ab.fluorochrome.name if ab.fluorochrome else None
        ul_per_test = comp.ul_per_test()
        needed = round(ul_per_test * total_tests, 3)
        current = get_total_stock_ul(comp.antibody_id, session)
        remaining = round(current - needed, 3)

        fc = forecast_antibody(comp.antibody_id, session, current_stock_ul=max(remaining, 0))
        days_after = fc.days_remaining
        threshold = _get_threshold(comp.antibody_id, session)
        has_warning = remaining < 0 or (days_after is not None and days_after < threshold)

        preview_components.append(ComponentPreview(
            antibody_id=ab.id,
            antibody_name=ab.name,
            fluorochrome=fluor,
            vendor=ab.vendor,
            volume_per_tube_ul=comp.volume_per_tube_ul,
            tubes_per_test=comp.tubes_per_test,
            ul_per_test=ul_per_test,
            total_ul_needed=needed,
            current_stock_ul=current,
            remaining_after_ul=remaining,
            has_warning=has_warning,
        ))

        if has_warning:
            severity = "insufficient" if remaining < 0 else "warning"
            if severity == "insufficient":
                can_proceed = False
            affected = _other_panels_using(comp.antibody_id, panel.id, session)
            warnings.append(ComponentWarning(
                antibody_id=ab.id,
                antibody_name=ab.name,
                fluorochrome=fluor,
                needed_ul=needed,
                current_stock_ul=current,
                remaining_after_ul=remaining,
                days_remaining_after=round(days_after, 1) if days_after else None,
                alert_threshold_days=threshold,
                severity=severity,
                affected_panels=affected,
            ))

    return CocktailPreviewResponse(
        panel_id=panel.id,
        panel_name=panel.name,
        total_tests=total_tests,
        components=preview_components,
        warnings=warnings,
        can_proceed=can_proceed,
    )


def _enrich_cocktail(c, session):
    panel = session.get(Panel, c.panel_id)
    user = session.get(User, c.prepared_by)
    pct = round(c.remaining_tests / c.total_tests * 100, 1) if c.total_tests else 0
    reserved = c.reserved_tests or 0
    available = max(0, c.remaining_tests - reserved)
    return CocktailRead(
        id=c.id,
        cocktail_code=c.cocktail_code,
        panel_id=c.panel_id,
        panel_name=panel.name if panel else "unknown",
        prepared_by=c.prepared_by,
        prepared_by_username=user.username if user else "unknown",
        prepared_by_staff_id=c.prepared_by_staff_id,
        prepared_by_name=prepared_by_name(c, session),
        prepared_at=c.created_at.isoformat(timespec="minutes") if c.created_at else None,
        prepared_date=str(c.prepared_date),
        total_tests=c.total_tests,
        remaining_tests=c.remaining_tests,
        reserved_tests=reserved,
        available_tests=available,
        expiry_date=str(c.expiry_date) if c.expiry_date else None,
        lot_notes=c.lot_notes,
        active=c.active,
        pct_remaining=pct,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/preview", response_model=CocktailPreviewResponse)
def preview_cocktail(
    payload: CocktailPreviewRequest,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    panel = session.get(Panel, payload.panel_id)
    if not panel or not panel.active:
        raise HTTPException(status_code=404, detail="Panel not found")
    if payload.total_tests < 1:
        raise HTTPException(status_code=400, detail="total_tests must be >= 1")
    components = session.exec(
        select(PanelComponent).where(PanelComponent.panel_id == panel.id)
    ).all()
    return _build_preview(panel, components, payload.total_tests, session)


@router.get("/", response_model=List[CocktailRead])
def list_cocktails(
    panel_id: Optional[int] = None,
    active_only: bool = True,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    prepared_by_staff_id: Optional[int] = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(Cocktail)
    if panel_id:
        q = q.where(Cocktail.panel_id == panel_id)
    if active_only:
        q = q.where(Cocktail.active == True)
    if start_date:
        q = q.where(Cocktail.prepared_date >= start_date)
    if end_date:
        q = q.where(Cocktail.prepared_date <= end_date)
    if prepared_by_staff_id:
        q = q.where(Cocktail.prepared_by_staff_id == prepared_by_staff_id)
    cocktails = session.exec(q.order_by(Cocktail.prepared_date.desc(), Cocktail.created_at.desc())).all()
    return [_enrich_cocktail(c, session) for c in cocktails]


@router.post("/", response_model=CocktailRead, status_code=201)
def prepare_cocktail(
    payload: CocktailCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    panel = session.get(Panel, payload.panel_id)
    if not panel or not panel.active:
        raise HTTPException(status_code=404, detail="Panel not found")
    if payload.total_tests < 1:
        raise HTTPException(status_code=400, detail="total_tests must be >= 1")
    components = session.exec(
        select(PanelComponent).where(PanelComponent.panel_id == panel.id)
    ).all()
    if not components:
        raise HTTPException(status_code=400, detail="Panel has no components defined")
    if payload.prepared_by_staff_id is not None:
        from app.models import Staff
        staff = session.get(Staff, payload.prepared_by_staff_id)
        if not staff or not staff.active:
            raise HTTPException(status_code=400, detail="Prepared-by staff member not found or inactive")

    result = prepare(
        panel_id=panel.id,
        test_count=payload.total_tests,
        prepared_date=date.today(),
        prepared_by_user_id=current_user.id,
        session=session,
        expiry_date=payload.expiry_date,
        lot_notes=payload.lot_notes,
        prepared_by_staff_id=payload.prepared_by_staff_id,
    )
    session.commit()
    session.refresh(result.cocktail)
    enriched = _enrich_cocktail(result.cocktail, session)

    if result.shortfalls:
        data = enriched.model_dump()
        data["warnings"] = [s.describe() for s in result.shortfalls]
        return JSONResponse(status_code=207, content=data)
    return enriched


@router.post("/{cocktail_id}/use", response_model=CocktailRead)
def use_cocktail(
    cocktail_id: int,
    payload: CocktailUsageCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    cocktail = session.get(Cocktail, cocktail_id)
    if not cocktail or not cocktail.active:
        raise HTTPException(status_code=404, detail="Cocktail not found or exhausted")
    if payload.count < 1:
        raise HTTPException(status_code=400, detail="count must be >= 1")
    available = cocktail.remaining_tests - (cocktail.reserved_tests or 0)
    if payload.count > available:
        reserved = cocktail.reserved_tests or 0
        detail = f"Only {available} test(s) available to log"
        if reserved:
            detail += f" ({cocktail.remaining_tests} remaining − {reserved} reserved for sample orders)"
        raise HTTPException(status_code=400, detail=detail)
    usage = CocktailUsageLog(
        cocktail_id=cocktail.id,
        test_date=payload.test_date,
        count=payload.count,
        entered_by=current_user.id,
        notes=payload.notes,
    )
    session.add(usage)
    cocktail.remaining_tests -= payload.count
    if cocktail.remaining_tests <= 0:
        cocktail.remaining_tests = 0
        cocktail.active = False
    session.add(cocktail)
    session.commit()
    session.refresh(cocktail)
    return _enrich_cocktail(cocktail, session)


@router.get("/export/summary.csv", response_class=StreamingResponse)
def export_cocktail_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """CSV of cocktails prepared within an optional date range."""
    import csv, io
    from datetime import datetime as _dt

    q = select(Cocktail).order_by(Cocktail.prepared_date.desc())
    if start_date:
        q = q.where(Cocktail.prepared_date >= start_date)
    if end_date:
        q = q.where(Cocktail.prepared_date <= end_date)
    cocktails = session.exec(q).all()

    rows = []
    for c in cocktails:
        panel = session.get(Panel, c.panel_id) if c.panel_id else None
        prep_user = session.get(User, c.prepared_by)
        usage = session.exec(
            select(CocktailUsageLog).where(CocktailUsageLog.cocktail_id == c.id)
        ).all()
        tests_used = sum(u.count for u in usage)
        rows.append({
            "cocktail_id": c.id,
            "cocktail_code": c.cocktail_code or "",
            "panel": panel.name if panel else "",
            "test_code": panel.test_code if panel else "",
            "prepared_date": c.prepared_date.strftime("%Y-%m-%d"),
            "prepared_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
            "prepared_by": prepared_by_name(c, session) or "",
            "login": prep_user.username if prep_user else "",
            "total_tests": c.total_tests,
            "tests_used": tests_used,
            "remaining_tests": c.remaining_tests,
            "expiry_date": c.expiry_date.strftime("%Y-%m-%d") if c.expiry_date else "",
            "active": c.active,
            "lot_notes": c.lot_notes or "",
        })

    if not rows:
        rows = [{}]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys() if rows[0] else ["cocktail_id"])
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="flowjai_cocktails_summary_{ts}.csv"'},
    )


# ---------------------------------------------------------------------------
# Traceability — samples run on a cocktail, its antibody lots / shipments,
# and other cocktails that share those lots
# ---------------------------------------------------------------------------

@router.get("/{cocktail_id}/trace")
def trace_cocktail(
    cocktail_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    from app.services.traceability import cocktail_trace
    try:
        return cocktail_trace(cocktail_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{cocktail_id}/trace.csv", response_class=StreamingResponse)
def trace_cocktail_csv(
    cocktail_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """One row per sample tube run on (or reserved against) the cocktail, with the
    cocktail's antibody lots / shipments repeated on every row for filing."""
    import csv, io
    from datetime import datetime as _dt
    from app.services.traceability import cocktail_trace
    try:
        t = cocktail_trace(cocktail_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    c = t["cocktail"]
    reagents = "; ".join(
        f'{r["antibody_name"]}{"-" + r["fluorochrome"] if r["fluorochrome"] else ""} '
        f'lot {r["lot_no"]} shipment {r["shipment_id"] or "-"}'
        for r in t["components"]
    )
    fields = ["cocktail_code", "cocktail_id", "test_code", "prepared_date", "lab_id",
              "tube_status", "order_status", "processing_started_at", "completed_at",
              "pathologist", "technologist", "antibody_lots"]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for smp in t["samples"]:
        w.writerow({
            "cocktail_code": c["cocktail_code"] or "",
            "cocktail_id": c["id"],
            "test_code": smp["test_code"] or "",
            "prepared_date": c["prepared_date"] or "",
            "lab_id": smp["lab_id"],
            "tube_status": smp["tube_status"],
            "order_status": smp["order_status"],
            "processing_started_at": smp["processing_started_at"] or "",
            "completed_at": smp["completed_at"] or "",
            "pathologist": smp["pathologist"] or "",
            "technologist": smp["technologist"] or "",
            "antibody_lots": reagents,
        })
    if t["untracked_tests"]:
        w.writerow({"cocktail_code": c["cocktail_code"] or "", "cocktail_id": c["id"],
                    "lab_id": f'[{t["untracked_tests"]} test(s) logged without lab IDs]',
                    "antibody_lots": reagents})
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    name = (c["cocktail_code"] or f'cocktail_{c["id"]}').replace("/", "-")
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="trace_{name}_{ts}.csv"'},
    )


@router.get("/{cocktail_id}", response_model=CocktailRead)
def get_cocktail(
    cocktail_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    cocktail = session.get(Cocktail, cocktail_id)
    if not cocktail:
        raise HTTPException(status_code=404, detail="Cocktail not found")
    return _enrich_cocktail(cocktail, session)


# ---------------------------------------------------------------------------
# Printable worksheet (HTML) + CSV summary export
# ---------------------------------------------------------------------------

@router.get("/{cocktail_id}/worksheet", response_class=HTMLResponse)
def cocktail_worksheet(
    cocktail_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Print-ready HTML worksheet: antibody, volume per test, total volume, checkbox."""
    from app.models import Fluorochrome, LabSetting

    cocktail = session.get(Cocktail, cocktail_id)
    if not cocktail:
        raise HTTPException(status_code=404, detail="Cocktail not found")
    panel = session.get(Panel, cocktail.panel_id) if cocktail.panel_id else None
    components = session.exec(
        select(PanelComponent).where(PanelComponent.panel_id == cocktail.panel_id)
    ).all()
    prep_user = session.get(User, cocktail.prepared_by)

    lab_setting = session.get(LabSetting, "lab_name")
    lab_name = lab_setting.value if lab_setting else "flowjAI Laboratory"

    # Lots actually drawn (FIFO) for this cocktail, per antibody
    from app.models import ConsumptionLog, StockLot
    lots_by_ab: dict = {}
    for log in session.exec(select(ConsumptionLog).where(ConsumptionLog.cocktail_id == cocktail.id)).all():
        lot = session.get(StockLot, log.stock_lot_id)
        if lot:
            label = f"{lot.lot_no} / {lot.shipment_id or '—'}"
            lots_by_ab.setdefault(log.antibody_id, [])
            if label not in lots_by_ab[log.antibody_id]:
                lots_by_ab[log.antibody_id].append(label)

    rows_html = ""
    for comp in components:
        ab = session.get(Antibody, comp.antibody_id)
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab and ab.fluorochrome_id else None
        per_test = comp.volume_per_tube_ul * comp.tubes_per_test
        total = round(per_test * cocktail.total_tests, 1)
        rows_html += f"""
        <tr>
          <td class="chk"><span class="box"></span></td>
          <td>{ab.name if ab else '—'}</td>
          <td>{fc.name if fc else '—'}</td>
          <td class="lot">{'<br>'.join(lots_by_ab.get(comp.antibody_id, [])) or '—'}</td>
          <td class="num">{per_test:.1f}</td>
          <td class="num">{total:.1f}</td>
          <td class="sig"></td>
        </tr>"""

    expiry = cocktail.expiry_date.strftime("%d %b %Y") if cocktail.expiry_date else "—"
    prepared = cocktail.prepared_date.strftime("%d %b %Y")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Cocktail Worksheet #{cocktail.id}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #1a1a1a; max-width: 800px; margin: 20px auto; padding: 0 20px; }}
  h1 {{ font-size: 18px; margin: 0 0 2px; }}
  .lab {{ font-size: 13px; color: #555; margin-bottom: 16px; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; font-size: 13px; margin-bottom: 18px; border: 1px solid #ddd; padding: 12px 16px; border-radius: 6px; }}
  .meta b {{ color: #333; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ border: 1px solid #ccc; padding: 7px 9px; text-align: left; }}
  th {{ background: #f3f4f6; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.chk {{ text-align: center; width: 36px; }}
  td.sig {{ width: 110px; }}
  td.lot {{ font-family: ui-monospace, Consolas, monospace; font-size: 11px; }}
  .box {{ display: inline-block; width: 15px; height: 15px; border: 1.5px solid #555; border-radius: 3px; }}
  .footer {{ margin-top: 24px; font-size: 12px; color: #555; display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }}
  .footer .line {{ border-top: 1px solid #888; padding-top: 4px; margin-top: 40px; }}
  .print-btn {{ margin: 10px 0 20px; padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; }}
  @media print {{ .print-btn {{ display: none; }} body {{ margin: 0; }} }}
</style></head>
<body>
  <button class="print-btn" onclick="window.print()">Print / Save as PDF</button>
  <h1>Cocktail Preparation Worksheet</h1>
  <div class="lab">{lab_name}</div>
  <div class="meta">
    <div><b>Cocktail:</b> {cocktail.cocktail_code or ''} (#{cocktail.id})</div>
    <div><b>Panel:</b> {panel.name if panel else '—'} {f'({panel.test_code})' if panel else ''}</div>
    <div><b>Prepared:</b> {prepared}</div>
    <div><b>Prepared by:</b> {prepared_by_name(cocktail, session) or '—'}</div>
    <div><b>Total tests:</b> {cocktail.total_tests}</div>
    <div><b>Expiry:</b> {expiry}</div>
    <div style="grid-column: 1 / -1;"><b>Lot notes:</b> {cocktail.lot_notes or '—'}</div>
  </div>
  <table>
    <thead><tr>
      <th>✓</th><th>Antibody</th><th>Fluorochrome</th><th>Lot / Shipment</th>
      <th style="text-align:right">µl / test</th>
      <th style="text-align:right">Total µl ({cocktail.total_tests} tests)</th>
      <th>Added by</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <div class="footer">
    <div class="line">Prepared by (sign / date)</div>
    <div class="line">Checked by (sign / date)</div>
  </div>
</body></html>"""
    return HTMLResponse(content=html)
