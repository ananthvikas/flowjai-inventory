"""
services/traceability.py — cocktail look-back for troubleshooting.

Given a cocktail, answer three questions:
  1. Which samples were run on it?            (worklist tubes)
  2. What went into it?                       (antibody lots + shipments, from
                                               the FIFO consumption records)
  3. Which OTHER cocktails share those lots?  (a reagent-lot problem would
                                               affect them too)

Limitation surfaced to the user as `untracked_tests`: tests logged on a
cocktail via Cocktails → "Log usage" carry a count but no lab IDs, so those
samples cannot be listed. Only worklist-driven usage is traceable per sample.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from sqlmodel import Session, select

from app.models import (
    Antibody, Cocktail, ConsumptionLog, Fluorochrome, Panel, SampleOrder,
    SampleOrderTube, Staff, StockLot, User,
)
from app.services.shipments import display_status, get_verification
from app.services.sample_flags import flag_labels


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _cocktail_header(c: Cocktail, session: Session) -> dict:
    panel = session.get(Panel, c.panel_id)
    from app.services.cocktails import prepared_by_name
    return {
        "id": c.id,
        "cocktail_code": c.cocktail_code,
        "panel_id": c.panel_id,
        "panel_name": panel.name if panel else None,
        "test_code": panel.test_code if panel else None,
        "prepared_date": _iso(c.prepared_date),
        "prepared_by": prepared_by_name(c, session),
        "prepared_at": c.created_at.isoformat(timespec="minutes") if c.created_at else None,
        "expiry_date": _iso(c.expiry_date),
        "total_tests": c.total_tests,
        "remaining_tests": c.remaining_tests,
        "reserved_tests": c.reserved_tests or 0,
        "active": c.active,
        "lot_notes": c.lot_notes,
    }


def _components(cocktail_id: int, session: Session) -> List[dict]:
    logs = session.exec(
        select(ConsumptionLog).where(ConsumptionLog.cocktail_id == cocktail_id)
    ).all()
    grouped: Dict[tuple, float] = defaultdict(float)
    for log in logs:
        grouped[(log.antibody_id, log.stock_lot_id)] += log.volume_consumed_ul

    out = []
    for (ab_id, lot_id), vol in grouped.items():
        ab = session.get(Antibody, ab_id)
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab and ab.fluorochrome_id else None
        lot = session.get(StockLot, lot_id)
        v = get_verification(ab_id, lot.shipment_id if lot else None, session)
        out.append({
            "antibody_id": ab_id,
            "antibody_name": ab.name if ab else f"antibody {ab_id}",
            "fluorochrome": fc.name if fc else None,
            "stock_lot_id": lot_id,
            "lot_no": lot.lot_no if lot else None,
            "shipment_id": lot.shipment_id if lot else None,
            "expiry_date": _iso(lot.expiry_date) if lot else None,
            "volume_ul": round(vol, 2),
            "shipment_verification_id": v.id if v else None,
            "shipment_verification_status": display_status(v),
        })
    out.sort(key=lambda r: (r["antibody_name"], r["lot_no"] or ""))
    return out


def _samples(cocktail_id: int, session: Session) -> List[dict]:
    tubes = session.exec(
        select(SampleOrderTube).where(SampleOrderTube.reserved_cocktail_id == cocktail_id)
    ).all()
    staff_cache: Dict[int, Optional[str]] = {}

    def staff_name(sid: Optional[int]) -> Optional[str]:
        if not sid:
            return None
        if sid not in staff_cache:
            s = session.get(Staff, sid)
            staff_cache[sid] = s.name if s else None
        return staff_cache[sid]

    out = []
    for t in tubes:
        o = session.get(SampleOrder, t.sample_order_id)
        if not o:
            continue
        panel = session.get(Panel, t.panel_id)
        out.append({
            "sample_order_id": o.id,
            "lab_id": o.lab_id,
            "tube_id": t.id,
            "test_code": panel.test_code if panel else None,
            "tube_status": t.status,          # reserved = not yet run; consumed = run
            "order_status": o.status,
            "priority": o.priority,
            "ordered_at": _iso(o.ordered_at),
            "processing_started_at": _iso(o.processing_started_at),
            "completed_at": _iso(o.completed_at),
            "pathologist": staff_name(o.requesting_pathologist_id),
            "technologist": staff_name(o.processing_technologist_id),
            "sample_comment": o.sample_comment,
            "sample_flags": flag_labels(o.sample_flags),
        })
    # run samples in processing order first, then still-reserved ones
    out.sort(key=lambda r: (r["tube_status"] != "consumed", r["processing_started_at"] or "", r["lab_id"]))
    return out


def _related_cocktails(cocktail_id: int, components: List[dict], session: Session) -> List[dict]:
    lot_ids = {c["stock_lot_id"] for c in components}
    if not lot_ids:
        return []
    lot_label = {c["stock_lot_id"]: f'{c["antibody_name"]} lot {c["lot_no"]}' for c in components}

    logs = session.exec(
        select(ConsumptionLog)
        .where(ConsumptionLog.stock_lot_id.in_(lot_ids))
        .where(ConsumptionLog.cocktail_id != None)          # noqa: E711
        .where(ConsumptionLog.cocktail_id != cocktail_id)
    ).all()
    shared: Dict[int, set] = defaultdict(set)
    for log in logs:
        shared[log.cocktail_id].add(log.stock_lot_id)

    out = []
    for cid, lots in shared.items():
        c = session.get(Cocktail, cid)
        if not c:
            continue
        panel = session.get(Panel, c.panel_id)
        run = session.exec(
            select(SampleOrderTube)
            .where(SampleOrderTube.reserved_cocktail_id == cid)
            .where(SampleOrderTube.status == "consumed")
        ).all()
        out.append({
            "id": c.id,
            "cocktail_code": c.cocktail_code,
            "test_code": panel.test_code if panel else None,
            "prepared_date": _iso(c.prepared_date),
            "active": c.active,
            "samples_run": len(run),
            "shared_lots": sorted(lot_label.get(l, str(l)) for l in lots),
        })
    out.sort(key=lambda r: r["prepared_date"] or "", reverse=True)
    return out


def cocktail_trace(cocktail_id: int, session: Session) -> dict:
    c = session.get(Cocktail, cocktail_id)
    if not c:
        raise ValueError("Cocktail not found")
    components = _components(c.id, session)
    samples = _samples(c.id, session)
    consumed_via_worklist = sum(1 for s in samples if s["tube_status"] == "consumed")
    tests_used = max(0, c.total_tests - c.remaining_tests)
    return {
        "cocktail": _cocktail_header(c, session),
        "components": components,
        "samples": samples,
        "samples_run": consumed_via_worklist,
        "samples_reserved": sum(1 for s in samples if s["tube_status"] == "reserved"),
        "tests_used": tests_used,
        # tests logged without lab IDs (Cocktails → Log usage) — not traceable per sample
        "untracked_tests": max(0, tests_used - consumed_via_worklist),
        "related_cocktails": _related_cocktails(c.id, components, session),
    }
