"""
routers/tests.py — Test log entry and LIMS CSV import.

Creating a TestLog auto-triggers consumption recording.

Shortfall handling (revised):
  services/consumption.record_consumption now deducts EVERY panel component
  before reporting shortfalls, so a short antibody no longer causes the rest of
  the panel to be silently skipped. When shortfalls occur we:
    - keep the deductions that were possible,
    - append a machine-readable audit marker to the test log notes so the
      episode is recoverable later,
    - return 207 Multi-Status with the per-antibody warning list.

  Lab operations can't be halted because of a stock-data error — flag it,
  record what's possible, alert the team.
"""

import csv
import io
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_technologist_or_admin
from app.database import get_session
from app.models import ConsumptionLog, Panel, TestLog, User
from app.services.alerts import run_alert_check
from app.services.consumption import InsufficientStockError, record_consumption

router = APIRouter(prefix="/api/tests", tags=["tests"])

# Marker written into TestLog.notes when a run could not be fully deducted.
SHORTFALL_MARKER = "[STOCK SHORTFALL]"
NOTES_MAX_LEN = 512


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TestLogCreate(BaseModel):
    date: date
    panel_id: int
    count: int
    notes: Optional[str] = None


class ConsumptionRead(BaseModel):
    antibody_id: int
    stock_lot_id: int
    volume_consumed_ul: float


class TestLogRead(BaseModel):
    id: int
    date: date
    panel_id: Optional[int] = None
    panel_name: str
    count: int
    entry_method: str
    entered_by: int
    notes: Optional[str]
    source: str = "panel"          # "panel" | "adhoc" | "cocktail"
    consumption: List[ConsumptionRead] = []
    warnings: List[str] = []


class BulkImportResult(BaseModel):
    created: int
    skipped: int
    errors: List[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append_audit_note(log: TestLog, warnings: List[str]) -> None:
    """
    Record the shortfall on the test log itself so the incomplete deduction is
    traceable after the fact. Without this, a shortfall is only ever visible in
    the HTTP response and disappears the moment the browser tab closes.
    """
    if not warnings:
        return
    marker = f" {SHORTFALL_MARKER} " + "; ".join(warnings)
    base = log.notes or ""
    combined = (base + marker).strip()
    if len(combined) > NOTES_MAX_LEN:
        combined = combined[: NOTES_MAX_LEN - 3] + "..."
    log.notes = combined


def _enrich_log(log: TestLog, session: Session, warnings: List[str] = None) -> TestLogRead:
    panel = session.get(Panel, log.panel_id) if log.panel_id else None
    cons = session.exec(
        select(ConsumptionLog).where(ConsumptionLog.test_log_id == log.id)
    ).all()
    adhoc_label = getattr(log, "panel_name_adhoc", None)
    if panel:
        display_name = panel.name
        source = "panel"
    elif adhoc_label:
        display_name = adhoc_label
        source = "adhoc"
    else:
        display_name = "Ad hoc"
        source = "adhoc"
    return TestLogRead(
        id=log.id,
        date=log.test_date,
        panel_id=log.panel_id,
        panel_name=display_name,
        count=log.count,
        entry_method=log.entry_method,
        entered_by=log.entered_by,
        notes=log.notes,
        source=source,
        consumption=[
            ConsumptionRead(
                antibody_id=c.antibody_id,
                stock_lot_id=c.stock_lot_id,
                volume_consumed_ul=c.volume_consumed_ul,
            )
            for c in cons
        ],
        warnings=warnings or [],
    )


def _create_and_record(
    payload: TestLogCreate,
    entry_method: str,
    current_user: User,
    session: Session,
) -> tuple[TestLog, list[str]]:
    """
    Core logic shared by manual entry and CSV import.

    record_consumption processes every component before raising, so by the time
    InsufficientStockError arrives all possible deductions are already in the
    session and the caller can commit.
    """
    panel = session.get(Panel, payload.panel_id)
    if not panel or not panel.active:
        raise HTTPException(status_code=404, detail="Panel not found or inactive")

    if payload.count <= 0:
        raise HTTPException(status_code=400, detail="count must be > 0")

    log = TestLog(
        test_date=payload.date,
        panel_id=payload.panel_id,
        count=payload.count,
        entry_method=entry_method,
        entered_by=current_user.id,
        notes=payload.notes,
    )
    session.add(log)
    session.flush()  # get log.id without committing

    warnings: List[str] = []
    try:
        record_consumption(log, session)
    except InsufficientStockError as e:
        warnings = e.messages()
        _append_audit_note(log, warnings)
        session.add(log)

    return log, warnings


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[TestLogRead])
def list_test_logs(
    panel_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 100,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(TestLog).order_by(TestLog.test_date.desc()).limit(limit)
    if panel_id:
        q = q.where(TestLog.panel_id == panel_id)
    if start_date:
        q = q.where(TestLog.test_date >= start_date)
    if end_date:
        q = q.where(TestLog.test_date <= end_date)
    logs = session.exec(q).all()
    result = [_enrich_log(log, session) for log in logs]

    # Merge in cocktail usage as unified test-log entries (read-only view)
    from app.models import Cocktail, CocktailUsageLog
    cq = select(CocktailUsageLog).order_by(CocktailUsageLog.test_date.desc()).limit(limit)
    if start_date:
        cq = cq.where(CocktailUsageLog.test_date >= start_date)
    if end_date:
        cq = cq.where(CocktailUsageLog.test_date <= end_date)
    usage_logs = session.exec(cq).all()
    for u in usage_logs:
        cocktail = session.get(Cocktail, u.cocktail_id)
        panel = session.get(Panel, cocktail.panel_id) if cocktail and cocktail.panel_id else None
        label = f"{panel.name if panel else 'Cocktail'} (cocktail)"
        result.append(TestLogRead(
            id=100_000_000 + u.id,   # offset to avoid id collision with TestLog
            date=u.test_date,
            panel_id=None,
            panel_name=label,
            count=u.count,
            entry_method="cocktail_use",
            entered_by=u.entered_by,
            notes=u.notes,
            source="cocktail",
            consumption=[],
            warnings=[],
        ))

    result.sort(key=lambda r: r.date, reverse=True)
    return result[:limit]


@router.post("/", response_model=TestLogRead, status_code=201)
def create_test_log(
    payload: TestLogCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    log, warnings = _create_and_record(payload, "manual", current_user, session)

    # Run alert check after consumption — never let alert failure block logging
    try:
        run_alert_check(session)
    except Exception:
        pass

    session.commit()

    result = _enrich_log(log, session, warnings)
    if warnings:
        # 207 so the frontend knows the run was recorded but not fully deducted
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=207, content=result.model_dump(mode="json"))
    return result


@router.post("/import-csv", response_model=BulkImportResult)
async def import_csv(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """
    CSV format (header required):
      date,test_code,count,notes
      2024-06-01,BMRD,12,
      2024-06-01,LSS,8,Monday batch

    date: YYYY-MM-DD
    test_code: must match an active panel's test_code
    count: integer > 0
    notes: optional
    """
    content = await file.read()
    text = content.decode("utf-8-sig")  # strip BOM if Excel-exported
    reader = csv.DictReader(io.StringIO(text))

    created = 0
    skipped = 0
    errors: List[str] = []

    required_cols = {"date", "test_code", "count"}
    if not required_cols.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns: {required_cols}. Found: {reader.fieldnames}",
        )

    for i, row in enumerate(reader, start=2):
        try:
            panel = session.exec(
                select(Panel).where(Panel.test_code == row["test_code"].strip())
            ).first()
            if not panel:
                errors.append(f"Row {i}: unknown test_code '{row['test_code']}'")
                skipped += 1
                continue

            count = int(row["count"])
            if count <= 0:
                errors.append(f"Row {i}: count must be > 0")
                skipped += 1
                continue

            _, warnings = _create_and_record(
                payload=TestLogCreate(
                    date=date.fromisoformat(row["date"].strip()),
                    panel_id=panel.id,
                    count=count,
                    notes=row.get("notes", "").strip() or None,
                ),
                entry_method="lims_import",
                current_user=current_user,
                session=session,
            )
            if warnings:
                errors.extend([f"Row {i} warning: {w}" for w in warnings])
            created += 1

        except (ValueError, KeyError) as e:
            errors.append(f"Row {i}: {str(e)}")
            skipped += 1

    try:
        run_alert_check(session)
    except Exception:
        pass
    session.commit()

    return BulkImportResult(created=created, skipped=skipped, errors=errors)


# ---------------------------------------------------------------------------
# Ad hoc test log — individual antibody selection, no panel required
# ---------------------------------------------------------------------------

class AdhocItem(BaseModel):
    antibody_id: int
    volume_ul: float          # total µl consumed for this antibody in this run


class AdhocTestLogCreate(BaseModel):
    date: date
    label: str                # free-text label shown instead of panel name
    count: int = 1
    notes: Optional[str] = None
    items: List[AdhocItem]


@router.post("/adhoc", status_code=201)
def create_adhoc_test_log(
    payload: AdhocTestLogCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """
    Log a test run using individually chosen antibodies rather than a saved panel.
    Useful for one-off panels, custom combinations, or QC runs.

    Every item is deducted regardless of whether an earlier item was short —
    same contract as panel-based consumption.
    """
    from app.models import Antibody
    from app.services.consumption import _deduct_from_lots

    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one antibody item is required")
    if payload.count <= 0:
        raise HTTPException(status_code=400, detail="count must be > 0")

    log = TestLog(
        test_date=payload.date,
        panel_id=None,
        panel_name_adhoc=payload.label,
        count=payload.count,
        entry_method="adhoc_manual",
        entered_by=current_user.id,
        notes=payload.notes,
    )
    session.add(log)
    session.flush()

    warnings: List[str] = []
    for item in payload.items:
        total_ul = round(item.volume_ul * payload.count, 3)
        try:
            _, shortfall = _deduct_from_lots(
                antibody_id=item.antibody_id,
                total_ul=total_ul,
                test_log=log,
                session=session,
            )
            if shortfall > 0:
                ab = session.get(Antibody, item.antibody_id)
                name = ab.name if ab else f"id={item.antibody_id}"
                warnings.append(
                    f"{name}: needed {total_ul:.1f} µl, short by {shortfall:.1f} µl "
                    f"(stock now recorded as exhausted)"
                )
        except Exception as e:  # never abandon the remaining items
            warnings.append(f"antibody id={item.antibody_id}: {e}")

    _append_audit_note(log, warnings)
    session.add(log)

    try:
        run_alert_check(session)
    except Exception:
        pass
    session.commit()

    return {"test_log_id": log.id, "warnings": warnings}
