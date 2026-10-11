"""
routers/sample_orders.py — the worklist. Replaces the staff Google sheet.

Flow:
  POST /api/sample-orders/                 create order + reserve cocktail tests
  POST /api/sample-orders/{id}/reserve     retry reservation (after a cocktail prep)
  POST /api/sample-orders/{id}/start       in_queue -> in_processing (consume cocktail)
  POST /api/sample-orders/{id}/complete    in_processing -> completed
  POST /api/sample-orders/{id}/cancel      release reservations, mark cancelled
  GET  /api/sample-orders/                 worklist (pending on top)
  GET  /api/sample-orders/cocktail-availability   per-panel free cocktail tests
  GET  /api/sample-orders/export/worklist.csv     full step log + TAT
"""

import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_technologist_or_admin
from app.database import get_session
from app.models import (
    Cocktail, Panel, SampleOrder, SampleOrderTube, Staff, User,
)
from app.services.sample_flags import SAMPLE_FLAGS, flag_labels, parse_flags, set_flag
from app.services.processing import (
    StepError, complete_step, ensure_tube_steps, next_step, step_progress,
)
from app.services.sample_orders import (
    cocktail_available_tests, release_tube, reserve_order, unreserved_tubes,
)

router = APIRouter(prefix="/api/sample-orders", tags=["sample-orders"])

STATUS_RANK = {"in_queue": 0, "in_processing": 1, "completed": 2, "cancelled": 3}
PRIORITY_RANK = {"urgent": 0, "routine": 1}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TubeIn(BaseModel):
    panel_id: int


class SampleOrderCreate(BaseModel):
    lab_id: str
    requesting_pathologist_id: Optional[int] = None
    processing_technologist_id: Optional[int] = None
    priority: str = "routine"
    notes: Optional[str] = None
    ordered_at: Optional[datetime] = None
    tubes: List[TubeIn]


class SampleOrderUpdate(BaseModel):
    lab_id: Optional[str] = None
    requesting_pathologist_id: Optional[int] = None
    processing_technologist_id: Optional[int] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    ordered_at: Optional[datetime] = None


class TubeRead(BaseModel):
    id: int
    panel_id: int
    panel_name: str
    test_code: str
    status: str
    reserved_cocktail_id: Optional[int]
    cocktail_code: Optional[str]
    cocktail_label: Optional[str]
    steps_done: int = 0
    steps_total: int = 0
    current_step: Optional[str] = None


class SampleOrderRead(BaseModel):
    id: int
    lab_id: str
    requesting_pathologist_id: Optional[int]
    requesting_pathologist_name: Optional[str]
    processing_technologist_id: Optional[int]
    processing_technologist_name: Optional[str]
    status: str
    priority: str
    notes: Optional[str]
    sample_comment: Optional[str] = None
    sample_comment_updated_at: Optional[str] = None
    sample_comment_updated_by: Optional[str] = None      # login (shared on the bench PC)
    sample_comment_staff_name: Optional[str] = None      # the person, from the staff picker
    sample_flags: List[str] = []                         # codes, e.g. ["fibrin", "low_volume"]
    sample_flags_updated_at: Optional[str] = None
    sample_flags_staff_name: Optional[str] = None
    ordered_at: Optional[str]
    processing_started_at: Optional[str]
    completed_at: Optional[str]
    created_by: int
    tubes: List[TubeRead]
    tube_count: int
    reserved_count: int
    awaiting_count: int
    consumed_count: int
    tat_minutes: Optional[float]


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _staff_name(staff_id: Optional[int], session: Session) -> Optional[str]:
    if not staff_id:
        return None
    s = session.get(Staff, staff_id)
    return s.name if s else None


def _require_staff(staff_id: Optional[int], session: Session) -> Staff:
    """Shared logins: every comment / flag change names the person doing it."""
    if staff_id is None:
        raise HTTPException(status_code=400, detail="Choose who is making this change (staff name)")
    s = session.get(Staff, staff_id)
    if not s or not s.active:
        raise HTTPException(status_code=400, detail="Staff member not found or inactive")
    return s


def _enrich(order: SampleOrder, session: Session) -> SampleOrderRead:
    tubes = session.exec(
        select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)
    ).all()
    patho = session.get(Staff, order.requesting_pathologist_id) if order.requesting_pathologist_id else None
    tech = session.get(Staff, order.processing_technologist_id) if order.processing_technologist_id else None

    tube_reads: List[TubeRead] = []
    reserved = awaiting = consumed = 0
    for t in tubes:
        panel = session.get(Panel, t.panel_id)
        label = None
        cocktail_code = None
        if t.reserved_cocktail_id:
            c = session.get(Cocktail, t.reserved_cocktail_id)
            if c:
                cocktail_code = c.cocktail_code
                label = f"#{c.id} (prep {c.prepared_date})"
        if t.status == "reserved":
            reserved += 1
        elif t.status == "awaiting_cocktail":
            awaiting += 1
        elif t.status == "consumed":
            consumed += 1
        tube_reads.append(TubeRead(
            id=t.id,
            panel_id=t.panel_id,
            panel_name=panel.name if panel else f"panel {t.panel_id}",
            test_code=panel.test_code if panel else "",
            status=t.status,
            reserved_cocktail_id=t.reserved_cocktail_id,
            cocktail_code=cocktail_code,
            cocktail_label=label,
            **step_progress(t, session),
        ))

    commenter = session.get(User, order.sample_comment_updated_by) if order.sample_comment_updated_by else None

    tat = None
    if order.completed_at and order.ordered_at:
        tat = round((order.completed_at - order.ordered_at).total_seconds() / 60.0, 1)

    return SampleOrderRead(
        id=order.id,
        lab_id=order.lab_id,
        requesting_pathologist_id=order.requesting_pathologist_id,
        requesting_pathologist_name=patho.name if patho else None,
        processing_technologist_id=order.processing_technologist_id,
        processing_technologist_name=tech.name if tech else None,
        status=order.status,
        priority=order.priority,
        notes=order.notes,
        sample_comment=order.sample_comment,
        sample_comment_updated_at=_iso(order.sample_comment_updated_at),
        sample_comment_updated_by=commenter.username if commenter else None,
        sample_comment_staff_name=_staff_name(order.sample_comment_staff_id, session),
        sample_flags=parse_flags(order.sample_flags),
        sample_flags_updated_at=_iso(order.sample_flags_updated_at),
        sample_flags_staff_name=_staff_name(order.sample_flags_staff_id, session),
        ordered_at=_iso(order.ordered_at),
        processing_started_at=_iso(order.processing_started_at),
        completed_at=_iso(order.completed_at),
        created_by=order.created_by,
        tubes=tube_reads,
        tube_count=len(tube_reads),
        reserved_count=reserved,
        awaiting_count=awaiting,
        consumed_count=consumed,
        tat_minutes=tat,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/cocktail-availability")
def cocktail_availability(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Per-panel count of free (unreserved) cocktail tests — drives the tube picker."""
    from datetime import date
    today = date.today()
    cocktails = session.exec(select(Cocktail).where(Cocktail.active == True)).all()  # noqa: E712
    by_panel: dict[int, int] = {}
    for c in cocktails:
        if c.expiry_date is not None and c.expiry_date < today:
            continue
        by_panel[c.panel_id] = by_panel.get(c.panel_id, 0) + cocktail_available_tests(c)
    return by_panel


@router.get("/", response_model=List[SampleOrderRead])
def list_orders(
    status: Optional[str] = None,
    limit: int = 200,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date_field: str = "ordered_at",
    lab_id: Optional[str] = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    if date_field not in ("ordered_at", "completed_at"):
        raise HTTPException(status_code=400, detail="date_field must be 'ordered_at' or 'completed_at'")

    q = select(SampleOrder)
    if status:
        q = q.where(SampleOrder.status == status)
    if lab_id and lab_id.strip():
        # substring, case-insensitive (SQLite LIKE is case-insensitive for ASCII)
        q = q.where(SampleOrder.lab_id.like(f"%{lab_id.strip()}%"))

    orders = session.exec(q).all()

    # Date filtering — applied after fetch for consistency with the in-memory sort
    if start_date or end_date:
        filtered: list[SampleOrder] = []
        for o in orders:
            target = o.ordered_at if date_field == "ordered_at" else o.completed_at
            if target is None:
                continue
            target_str = target.date().isoformat()
            if start_date and target_str < start_date:
                continue
            if end_date and target_str > end_date:
                continue
            filtered.append(o)
        orders = filtered

    def sort_key(o: SampleOrder):
        rank = STATUS_RANK.get(o.status, 9)
        prio = PRIORITY_RANK.get(o.priority, 9)
        if o.status in ("in_queue", "in_processing"):
            # longest-waiting first: oldest request time ascending
            anchor = o.ordered_at or o.created_at
            return (rank, prio, anchor.timestamp() if anchor else 0.0)
        # closed orders: most recent first (negate to sort descending within group)
        anchor = o.completed_at or o.ordered_at or o.created_at
        return (rank, prio, -anchor.timestamp() if anchor else 0.0)

    orders.sort(key=sort_key)
    result = [_enrich(o, session) for o in orders[:limit]]
    session.commit()   # persist step copies back-filled for pre-existing tubes
    return result


@router.post("/", response_model=SampleOrderRead)
def create_order(
    payload: SampleOrderCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    if not payload.lab_id.strip():
        raise HTTPException(status_code=400, detail="lab_id is required")
    if not payload.tubes:
        raise HTTPException(status_code=400, detail="At least one tube is required")
    if payload.priority not in ("routine", "urgent"):
        raise HTTPException(status_code=400, detail="priority must be routine or urgent")

    # validate panels exist
    for t in payload.tubes:
        panel = session.get(Panel, t.panel_id)
        if not panel or not panel.active:
            raise HTTPException(status_code=404, detail=f"Panel {t.panel_id} not found or inactive")

    order = SampleOrder(
        lab_id=payload.lab_id.strip(),
        requesting_pathologist_id=payload.requesting_pathologist_id,
        processing_technologist_id=payload.processing_technologist_id,
        priority=payload.priority,
        notes=payload.notes,
        ordered_at=payload.ordered_at or datetime.now(),
        status="in_queue",
        created_by=current_user.id,
    )
    session.add(order)
    session.flush()  # get order.id

    for t in payload.tubes:
        session.add(SampleOrderTube(
            sample_order_id=order.id,
            panel_id=t.panel_id,
            status="awaiting_cocktail",
        ))
    session.flush()

    shortfalls = reserve_order(order, session)
    for tube in session.exec(select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)).all():
        ensure_tube_steps(tube, session, order)   # freeze this panel's steps for the tube
    session.commit()
    session.refresh(order)

    result = _enrich(order, session)
    if shortfalls:
        data = result.model_dump()
        data["cocktail_shortfalls"] = shortfalls
        return JSONResponse(status_code=207, content=data)
    return result


@router.get("/sample-flags")
def sample_flag_options(_: User = Depends(get_current_user)):
    """The tap-to-toggle flags, in display order (single source for the UI)."""
    return [{"code": c, "label": label} for c, label in SAMPLE_FLAGS.items()]


@router.get("/{order_id}", response_model=SampleOrderRead)
def get_order(
    order_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _enrich(order, session)


@router.patch("/{order_id}", response_model=SampleOrderRead)
def update_order(
    order_id: int,
    payload: SampleOrderUpdate,
    session: Session = Depends(get_session),
    _: User = Depends(require_technologist_or_admin),
):
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail="Cannot edit a closed order")
    data = payload.model_dump(exclude_none=True)
    if "priority" in data and data["priority"] not in ("routine", "urgent"):
        raise HTTPException(status_code=400, detail="priority must be routine or urgent")
    for k, v in data.items():
        setattr(order, k, v)
    session.add(order)
    session.commit()
    session.refresh(order)
    return _enrich(order, session)


class SampleCommentIn(BaseModel):
    comment: Optional[str] = None      # empty / null clears it
    staff_id: Optional[int] = None     # required — see _require_staff


class SampleFlagIn(BaseModel):
    on: bool                           # desired state (not a toggle: safe to retry)
    staff_id: Optional[int] = None     # required — see _require_staff


@router.put("/{order_id}/flags/{code}", response_model=SampleOrderRead)
def set_sample_flag(
    order_id: int,
    code: str,
    payload: SampleFlagIn,
    session: Session = Depends(get_session),
    _: User = Depends(require_technologist_or_admin),
):
    """Set one quality flag on or off. Allowed at any status."""
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    staff = _require_staff(payload.staff_id, session)
    try:
        new = set_flag(order.sample_flags, code, payload.on)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if new != order.sample_flags:           # a repeated tap changes nothing, records nothing
        order.sample_flags = new
        order.sample_flags_updated_at = datetime.now()
        order.sample_flags_staff_id = staff.id
        session.add(order)
        session.commit()
        session.refresh(order)
    return _enrich(order, session)


@router.put("/{order_id}/sample-comment", response_model=SampleOrderRead)
def set_sample_comment(
    order_id: int,
    payload: SampleCommentIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """Sample-quality remark (clots, fibrin, degeneration, low count…). Allowed at
    any status, including completed — problems are often noticed at acquisition."""
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    staff = _require_staff(payload.staff_id, session)
    text = (payload.comment or "").strip()
    if len(text) > 512:
        raise HTTPException(status_code=400, detail="Comment is limited to 512 characters")
    order.sample_comment = text or None
    order.sample_comment_updated_at = datetime.now()
    order.sample_comment_updated_by = current_user.id
    order.sample_comment_staff_id = staff.id
    session.add(order)
    session.commit()
    session.refresh(order)
    return _enrich(order, session)


@router.post("/{order_id}/reserve", response_model=SampleOrderRead)
def retry_reserve(
    order_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_technologist_or_admin),
):
    """Re-attempt reservation for awaiting tubes — use after a new cocktail is prepped."""
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "in_queue":
        raise HTTPException(status_code=409, detail="Only queued orders can reserve")
    shortfalls = reserve_order(order, session)
    session.commit()
    session.refresh(order)
    result = _enrich(order, session)
    if shortfalls:
        data = result.model_dump()
        data["cocktail_shortfalls"] = shortfalls
        return JSONResponse(status_code=207, content=data)
    return result


@router.post("/{order_id}/start", response_model=SampleOrderRead)
def start_processing(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """in_queue -> in_processing. Consumes reserved cocktail tests. Blocks if any
    tube still lacks a cocktail."""
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "in_queue":
        raise HTTPException(status_code=409, detail=f"Order is {order.status}, not in_queue")

    awaiting = unreserved_tubes(order, session)
    if awaiting:
        panels = []
        for t in awaiting:
            p = session.get(Panel, t.panel_id)
            panels.append(p.test_code if p else str(t.panel_id))
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start: no cocktail reserved for {len(awaiting)} tube(s): "
                   f"{', '.join(panels)}. Prepare a cocktail then retry reservation.",
        )

    # Same path the bench station uses: step 1 ("cocktail added") on every tube.
    tubes = session.exec(select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)).all()
    try:
        for t in tubes:
            nxt = next_step(ensure_tube_steps(t, session, order))
            if nxt is not None and nxt.seq == 1:
                complete_step(t, 1, user_id=current_user.id, session=session)
    except StepError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    session.commit()
    session.refresh(order)
    return _enrich(order, session)


@router.post("/{order_id}/complete", response_model=SampleOrderRead)
def complete_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """in_processing -> completed. Marks every remaining processing step done
    (fallback for when the bench station isn't used)."""
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "in_processing":
        raise HTTPException(status_code=409, detail=f"Order is {order.status}, not in_processing")
    tubes = session.exec(select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)).all()
    try:
        for t in tubes:
            while order.status != "completed":
                nxt = next_step(ensure_tube_steps(t, session, order))
                if nxt is None:
                    break
                complete_step(t, nxt.seq, user_id=current_user.id, session=session, force=True)
    except StepError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    if order.status != "completed":   # e.g. a tube never started — close regardless
        order.status = "completed"
        order.completed_at = datetime.now()
        session.add(order)
    session.commit()
    session.refresh(order)
    return _enrich(order, session)


@router.post("/{order_id}/cancel", response_model=SampleOrderRead)
def cancel_order(
    order_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_technologist_or_admin),
):
    """Cancel an order. Releases held reservations if still queued. Cocktail already
    consumed on in_processing orders is NOT refunded (it was physically pipetted)."""
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Order already {order.status}")

    # Release tests still only reserved (a tube not yet started on a partly
    # processed order included). Consumed tubes are not refunded.
    tubes = session.exec(
        select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)
    ).all()
    for t in tubes:
        if t.status in ("reserved", "awaiting_cocktail"):
            release_tube(t, session)

    order.status = "cancelled"
    session.add(order)
    session.commit()
    session.refresh(order)
    return _enrich(order, session)


@router.get("/export/worklist.csv", response_class=StreamingResponse)
def export_worklist(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """One row per order with all step timestamps and TAT intervals (minutes)."""
    orders = session.exec(select(SampleOrder).order_by(SampleOrder.ordered_at)).all()

    def mins(a, b):
        if a and b:
            return round((b - a).total_seconds() / 60.0, 1)
        return ""

    rows = []
    for o in orders:
        if start_date and o.ordered_at and o.ordered_at.date().isoformat() < start_date:
            continue
        if end_date and o.ordered_at and o.ordered_at.date().isoformat() > end_date:
            continue
        patho = session.get(Staff, o.requesting_pathologist_id) if o.requesting_pathologist_id else None
        tech = session.get(Staff, o.processing_technologist_id) if o.processing_technologist_id else None
        tubes = session.exec(
            select(SampleOrderTube).where(SampleOrderTube.sample_order_id == o.id)
        ).all()
        codes = []
        cocktail_codes = []
        for t in tubes:
            p = session.get(Panel, t.panel_id)
            codes.append(p.test_code if p else str(t.panel_id))
            if t.reserved_cocktail_id:
                c = session.get(Cocktail, t.reserved_cocktail_id)
                cocktail_codes.append(c.cocktail_code if c and c.cocktail_code else "")
            else:
                cocktail_codes.append("")
        rows.append({
            "order_id": o.id,
            "lab_id": o.lab_id,
            "status": o.status,
            "priority": o.priority,
            "pathologist": patho.name if patho else "",
            "technologist": tech.name if tech else "",
            "tubes": "; ".join(codes),
            "tube_count": len(tubes),
            "cocktail_codes": "; ".join(c for c in cocktail_codes if c),
            "ordered_at": _iso(o.ordered_at) or "",
            "processing_started_at": _iso(o.processing_started_at) or "",
            "completed_at": _iso(o.completed_at) or "",
            "queue_minutes": mins(o.ordered_at, o.processing_started_at),
            "processing_minutes": mins(o.processing_started_at, o.completed_at),
            "total_tat_minutes": mins(o.ordered_at, o.completed_at),
            "notes": o.notes or "",
            "sample_flags": "; ".join(flag_labels(o.sample_flags)),
            "sample_comment": o.sample_comment or "",
            "comment_by": _staff_name(o.sample_comment_staff_id, session) or "",
        })

    if not rows:
        rows = [{"order_id": "", "lab_id": "", "status": "", "priority": "",
                 "pathologist": "", "technologist": "", "tubes": "", "tube_count": "",
                 "cocktail_codes": "",
                 "ordered_at": "", "processing_started_at": "", "completed_at": "",
                 "queue_minutes": "", "processing_minutes": "", "total_tat_minutes": "",
                 "notes": "", "sample_flags": "", "sample_comment": "", "comment_by": ""}]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="flowjai_worklist_{ts}.csv"'},
    )
