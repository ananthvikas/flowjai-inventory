"""
routers/station.py — bench processing station (tablet) + step templates.

  GET  /api/station/queue                                 pending samples, oldest/urgent first
  POST /api/station/tubes/{tube_id}/steps/{seq}/complete  {staff_id}
  POST /api/station/tubes/{tube_id}/steps/{seq}/undo
  POST /api/station/orders/{order_id}/advance             {step_name, staff_id} — every tube waiting on that step
  GET  /api/station/templates                             step lists (lab default + per panel)
  PUT  /api/station/templates/default                     {names}   (admin)
  PUT  /api/station/templates/{panel_id}                  {names}   (admin; [] = use lab default)
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin, require_technologist_or_admin
from app.database import get_session
from app.models import (
    Cocktail, Panel, SampleOrder, SampleOrderTube, SampleOrderTubeStep, Staff, User,
)
from fastapi.responses import JSONResponse

from app.services.sample_flags import parse_flags

from app.services.processing import (
    DEFAULT_STEPS, StepError, TimerNotElapsed, apply_timers_to_live_tubes, can_undo,
    complete_step, ensure_tube_steps, last_done, next_step, ready_at, set_template,
    template_steps, undo_step,
)

router = APIRouter(prefix="/api/station", tags=["station"])

RECENT_MINUTES = 15   # completed samples stay visible briefly, for undo / recall


class StaffIn(BaseModel):
    staff_id: Optional[int] = None
    force: bool = False          # confirm completing a step before its timer ran out


class AdvanceIn(BaseModel):
    step_name: str
    staff_id: Optional[int] = None
    force: bool = False


class StepIn(BaseModel):
    name: str
    wait_minutes: Optional[int] = None


class TemplateIn(BaseModel):
    steps: Optional[List[StepIn]] = None
    names: Optional[List[str]] = None     # older clients: names only, no timers

    def payload(self):
        if self.steps is not None:
            return [s.model_dump() for s in self.steps]
        return self.names or []


def _timer_409(e: TimerNotElapsed) -> JSONResponse:
    return JSONResponse(status_code=409, content={
        "detail": str(e), "code": "timer_not_elapsed", "remaining_seconds": e.remaining_seconds,
    })


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _order_card(o: SampleOrder, session: Session, staff_names: Dict[int, str]) -> dict:
    now = datetime.now()
    tubes = session.exec(select(SampleOrderTube).where(SampleOrderTube.sample_order_id == o.id)).all()
    tube_cards = []
    for t in tubes:
        steps = ensure_tube_steps(t, session, o)
        panel = session.get(Panel, t.panel_id)
        cocktail = session.get(Cocktail, t.reserved_cocktail_id) if t.reserved_cocktail_id else None
        nxt, last = next_step(steps), last_done(steps)
        tube_cards.append({
            "id": t.id,
            "test_code": panel.test_code if panel else "",
            "panel_name": panel.name if panel else "",
            "status": t.status,
            "cocktail_code": cocktail.cocktail_code if cocktail else None,
            "steps": [
                {
                    "seq": s.seq,
                    "name": s.name,
                    "wait_minutes": s.wait_minutes,
                    "ready_at": (lambda r: r.isoformat(timespec="seconds") if r else None)(ready_at(steps, s)),
                    "completed_at": s.completed_at.isoformat(timespec="seconds") if s.completed_at else None,
                    "completed_by": staff_names.get(s.completed_by_staff_id) if s.completed_by_staff_id else None,
                    "completed_early_seconds": s.completed_early_seconds,
                }
                for s in steps
            ],
            "next_seq": nxt.seq if nxt else None,
            "next_name": nxt.name if nxt else None,
            "undo_seq": last.seq if last and can_undo(last, now) else None,
            "done": nxt is None,
        })
    anchor = o.ordered_at or o.created_at
    return {
        "id": o.id,
        "lab_id": o.lab_id,
        "priority": o.priority,
        "status": o.status,
        "notes": o.notes,
        "sample_flags": parse_flags(o.sample_flags),
        "sample_comment": o.sample_comment,
        "ordered_at": anchor.isoformat(timespec="seconds") if anchor else None,
        "waiting_minutes": round((now - anchor).total_seconds() / 60) if anchor else None,
        "completed_at": o.completed_at.isoformat(timespec="seconds") if o.completed_at else None,
        "pathologist": staff_names.get(o.requesting_pathologist_id),
        "technologist": staff_names.get(o.processing_technologist_id),
        "tubes": tube_cards,
    }


def _staff_names(session: Session) -> Dict[int, str]:
    return {s.id: s.name for s in session.exec(select(Staff)).all()}


def _check_staff(staff_id: Optional[int], session: Session) -> None:
    if staff_id is None:
        return
    s = session.get(Staff, staff_id)
    if not s or not s.active:
        raise HTTPException(status_code=400, detail="Staff member not found or inactive")


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

@router.get("/queue")
def queue(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    names = _staff_names(session)
    live = session.exec(
        select(SampleOrder).where(SampleOrder.status.in_(("in_queue", "in_processing")))
    ).all()
    # urgent first, then longest waiting
    live.sort(key=lambda o: (o.priority != "urgent", (o.ordered_at or o.created_at)))

    cutoff = datetime.now().timestamp() - RECENT_MINUTES * 60
    recent = session.exec(select(SampleOrder).where(SampleOrder.status == "completed")).all()
    recent = [o for o in recent if o.completed_at and o.completed_at.timestamp() >= cutoff]
    recent.sort(key=lambda o: o.completed_at, reverse=True)

    result = {
        "orders": [_order_card(o, session, names) for o in live],
        "recent": [_order_card(o, session, names) for o in recent[:6]],
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }
    session.commit()   # persist any back-filled step copies
    return result


def _tube_or_404(tube_id: int, session: Session) -> SampleOrderTube:
    t = session.get(SampleOrderTube, tube_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tube not found")
    return t


@router.post("/tubes/{tube_id}/steps/{seq}/complete")
def complete(
    tube_id: int,
    seq: int,
    payload: StaffIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    _check_staff(payload.staff_id, session)
    tube = _tube_or_404(tube_id, session)
    try:
        complete_step(tube, seq, user_id=current_user.id, session=session,
                      staff_id=payload.staff_id, force=payload.force)
    except TimerNotElapsed as e:
        session.rollback()
        return _timer_409(e)
    except StepError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    session.commit()
    order = session.get(SampleOrder, tube.sample_order_id)
    return _order_card(order, session, _staff_names(session))


@router.post("/tubes/{tube_id}/steps/{seq}/undo")
def undo(
    tube_id: int,
    seq: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_technologist_or_admin),
):
    tube = _tube_or_404(tube_id, session)
    try:
        undo_step(tube, seq, session)
    except StepError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    session.commit()
    order = session.get(SampleOrder, tube.sample_order_id)
    return _order_card(order, session, _staff_names(session))


@router.post("/orders/{order_id}/advance")
def advance(
    order_id: int,
    payload: AdvanceIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """Complete `step_name` on every tube of the order whose next step it is —
    the common case of processing all of a sample's tubes together."""
    _check_staff(payload.staff_id, session)
    order = session.get(SampleOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    tubes = session.exec(select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)).all()
    done = 0
    try:
        for t in tubes:
            nxt = next_step(ensure_tube_steps(t, session, order))
            if nxt is not None and nxt.name == payload.step_name:
                complete_step(t, nxt.seq, user_id=current_user.id, session=session,
                              staff_id=payload.staff_id, force=payload.force)
                done += 1
    except TimerNotElapsed as e:
        session.rollback()
        return _timer_409(e)
    except StepError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    if done == 0:
        raise HTTPException(status_code=409, detail=f"No tube is waiting on '{payload.step_name}'")
    session.commit()
    return _order_card(order, session, _staff_names(session))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/templates")
def templates(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    def block(panel_id):
        steps, source = template_steps(panel_id, session)
        return {"steps": steps, "names": [s["name"] for s in steps], "source": source}

    panels = session.exec(select(Panel).where(Panel.active == True).order_by(Panel.test_code)).all()  # noqa: E712
    return {
        "built_in": DEFAULT_STEPS,
        "default": block(None),
        "panels": [dict(block(p.id), panel_id=p.id, test_code=p.test_code, panel_name=p.name) for p in panels],
    }


@router.put("/templates/default", dependencies=[Depends(require_admin)])
def put_default(payload: TemplateIn, session: Session = Depends(get_session)):
    try:
        set_template(None, payload.payload(), session)
    except StepError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.flush()
    updated = apply_timers_to_live_tubes(session)
    session.commit()
    steps, source = template_steps(None, session)
    return {"steps": steps, "names": [s["name"] for s in steps], "source": source, "live_tubes_updated": updated}


@router.put("/templates/{panel_id}", dependencies=[Depends(require_admin)])
def put_panel(panel_id: int, payload: TemplateIn, session: Session = Depends(get_session)):
    if not session.get(Panel, panel_id):
        raise HTTPException(status_code=404, detail="Panel not found")
    try:
        set_template(panel_id, payload.payload(), session)
    except StepError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.flush()
    updated = apply_timers_to_live_tubes(session)
    session.commit()
    steps, source = template_steps(panel_id, session)
    return {"steps": steps, "names": [s["name"] for s in steps], "source": source, "live_tubes_updated": updated}
