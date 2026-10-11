"""routers/export.py — CSV export endpoints for antibodies, inventory, panels, cocktails."""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Antibody, Fluorochrome, StockLot, Panel, PanelComponent,
    Cocktail, CocktailUsageLog, User,
)

router = APIRouter(prefix="/api/export", tags=["export"])


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    """Return a StreamingResponse with CSV content and timestamped filename."""
    if not rows:
        rows = [{}]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    disposition = f'attachment; filename="{filename}_{ts}.csv"'
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": disposition},
    )


@router.get("/antibodies", dependencies=[Depends(get_current_user)])
def export_antibodies(session: Session = Depends(get_session)):
    antibodies = session.exec(select(Antibody)).all()
    rows = []
    for ab in antibodies:
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None
        rows.append({
            "name": ab.name,
            "clone": ab.clone or "",
            "vendor": ab.vendor or "",
            "catalog_no": ab.catalog_no or "",
            "vial_volume_ul": ab.vial_volume_ul if ab.vial_volume_ul is not None else "",
            "fluorochrome": fc.name if fc else "",
            "active": ab.active,
            "created_at": ab.created_at.strftime("%Y-%m-%d %H:%M") if ab.created_at else "",
        })
    rows.sort(key=lambda r: r["name"])
    return _csv_response(rows, "flowjai_antibodies")


@router.get("/inventory", dependencies=[Depends(get_current_user)])
def export_inventory(session: Session = Depends(get_session)):
    lots = session.exec(select(StockLot)).all()
    rows = []
    for lot in lots:
        ab = session.get(Antibody, lot.antibody_id)
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab and ab.fluorochrome_id else None
        rows.append({
            "antibody": ab.name if ab else "",
            "fluorochrome": fc.name if fc else "",
            "lot_no": lot.lot_no or "",
            # vendor / catalogue number live on the antibody, not the lot (the old
            # lot.vendor / lot.catalog_no / lot.received_date / lot.opened reads
            # raised AttributeError, so this export failed whenever a lot existed)
            "vendor": (ab.vendor if ab else None) or "",
            "catalog_no": (ab.catalog_no if ab else None) or "",
            "shipment_id": lot.shipment_id or "",
            "received_date": lot.date_received.strftime("%Y-%m-%d") if lot.date_received else "",
            "opened_date": lot.date_opened.strftime("%Y-%m-%d") if lot.date_opened else "",
            "expiry_date": lot.expiry_date.strftime("%Y-%m-%d") if lot.expiry_date else "",
            "standard_vial_volume_ul": (ab.vial_volume_ul if ab and ab.vial_volume_ul is not None else ""),
            "initial_volume_ul": lot.initial_volume_ul,
            "current_volume_ul": round(lot.current_volume_ul, 2),
            "active": lot.active,
            "notes": lot.notes or "",
        })
    rows.sort(key=lambda r: r["antibody"])
    return _csv_response(rows, "flowjai_inventory")


@router.get("/panels", dependencies=[Depends(get_current_user)])
def export_panels(session: Session = Depends(get_session)):
    panels = session.exec(select(Panel)).all()
    rows = []
    for panel in panels:
        comps = session.exec(
            select(PanelComponent).where(PanelComponent.panel_id == panel.id)
        ).all()
        if not comps:
            rows.append({
                "panel_name": panel.name,
                "test_code": panel.test_code,
                "test_group": panel.test_group or "",
                "department": panel.department or "",
                "active": panel.active,
                "antibody": "",
                "fluorochrome": "",
                "volume_per_tube_ul": "",
                "tubes_per_test": "",
                "ul_per_test": "",
            })
        for comp in comps:
            ab = session.get(Antibody, comp.antibody_id)
            fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab and ab.fluorochrome_id else None
            rows.append({
                "panel_name": panel.name,
                "test_code": panel.test_code,
                "test_group": panel.test_group or "",
                "department": panel.department or "",
                "active": panel.active,
                "antibody": ab.name if ab else "",
                "fluorochrome": fc.name if fc else "",
                "volume_per_tube_ul": comp.volume_per_tube_ul,
                "tubes_per_test": comp.tubes_per_test,
                "ul_per_test": round(comp.volume_per_tube_ul * comp.tubes_per_test, 2),
            })
    return _csv_response(rows, "flowjai_panels")


@router.get("/cocktails", dependencies=[Depends(get_current_user)])
def export_cocktails(session: Session = Depends(get_session)):
    cocktails = session.exec(select(Cocktail)).all()
    rows = []
    for c in cocktails:
        panel = session.get(Panel, c.panel_id) if c.panel_id else None
        usage_logs = session.exec(
            select(CocktailUsageLog).where(CocktailUsageLog.cocktail_id == c.id)
        ).all()
        rows.append({
            "cocktail_name": c.name,
            "panel": panel.name if panel else "",
            "prepared_at": c.prepared_at.strftime("%Y-%m-%d %H:%M") if c.prepared_at else "",
            "expiry_date": c.expiry_date.strftime("%Y-%m-%d") if c.expiry_date else "",
            "total_volume_ul": round(c.total_volume_ul, 2) if c.total_volume_ul else "",
            "remaining_volume_ul": round(c.remaining_volume_ul, 2) if c.remaining_volume_ul else "",
            "times_used": len(usage_logs),
            "notes": c.notes or "",
        })
    rows.sort(key=lambda r: r["cocktail_name"])
    return _csv_response(rows, "flowjai_cocktails")


@router.get("/stock-position", dependencies=[Depends(get_current_user)])
def export_stock_position(session: Session = Depends(get_session)):
    """
    Stores-facing stock position report.
    One row per antibody with total current stock, oldest expiry, and reorder flag.
    Deliberately omits internal IDs and system fields.
    """
    lots = session.exec(select(StockLot).where(StockLot.active == True)).all()

    # Group by antibody
    from collections import defaultdict
    grouped: dict = defaultdict(list)
    for lot in lots:
        grouped[lot.antibody_id].append(lot)

    rows = []
    for ab_id, ab_lots in grouped.items():
        ab = session.get(Antibody, ab_id)
        if not ab or not ab.active:
            continue
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None
        total_vol = sum(l.current_volume_ul for l in ab_lots)
        oldest_expiry = min(
            (l.expiry_date for l in ab_lots if l.expiry_date),
            default=None
        )
        rows.append({
            "antibody": ab.name,
            "fluorochrome": fc.name if fc else "",
            "vendor": ab.vendor or "",
            "catalog_no": ab.catalog_no or "",
            "current_stock_ul": round(total_vol, 1),
            "open_lots": len(ab_lots),
            "oldest_expiry": oldest_expiry.strftime("%Y-%m-%d") if oldest_expiry else "",
            "reorder_flag": "YES" if total_vol < 200 else "",
        })

    rows.sort(key=lambda r: r["antibody"])
    return _csv_response(rows, "flowjai_stock_position_stores")
