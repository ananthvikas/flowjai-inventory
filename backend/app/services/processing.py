"""
services/processing.py — bench processing steps (tablet station).

Model
-----
Every worklist tube carries its own ordered list of steps, copied from a
template when the tube is ordered:
    panel template  ->  lab default template  ->  built-in DEFAULT_STEPS

Rules
-----
* Steps are completed strictly in order, per tube.
* Step 1 means "cocktail added": completing it consumes the tube's reserved
  cocktail test (one CocktailUsageLog linked to the tube) and moves the order
  in_queue -> in_processing.
* When every step of every live tube is done, the order becomes completed.
* Only the most recent step of a tube can be undone, within UNDO_WINDOW. Undoing
  step 1 reverses the cocktail consumption exactly (the usage log is linked to
  the tube), so a mis-tap on the touchscreen doesn't corrupt stock counts.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from app.models import (
    Cocktail, CocktailUsageLog, PanelProcessStep, SampleOrder, SampleOrderTube,
    SampleOrderTubeStep,
)

DEFAULT_STEPS = ["Cocktail added", "Incubated", "Lysed & washed", "Acquired"]
UNDO_WINDOW = timedelta(minutes=10)
MAX_STEPS = 12
MAX_WAIT_MINUTES = 24 * 60


class StepError(ValueError):
    """Raised for rule violations; routers map it to HTTP 409."""


class TimerNotElapsed(StepError):
    """Step tapped before its wait time ran out; retry with force=True to confirm."""

    def __init__(self, step_name: str, remaining_seconds: int):
        self.remaining_seconds = remaining_seconds
        m, s = divmod(remaining_seconds, 60)
        super().__init__(f"'{step_name}' timer still has {m}:{s:02d} to run")


def _clean_steps(steps) -> List[dict]:
    """Accept ["name", ...] or [{"name", "wait_minutes"}, ...]."""
    out = []
    for st in steps or []:
        if isinstance(st, str):
            name, wait = st, None
        else:
            name, wait = st.get("name", ""), st.get("wait_minutes")
        name = (name or "").strip()[:64]
        if not name:
            continue
        if wait in ("", 0):
            wait = None
        if wait is not None:
            try:
                wait = int(wait)
            except (TypeError, ValueError):
                raise StepError(f"Wait time for '{name}' must be whole minutes")
            if wait < 0 or wait > MAX_WAIT_MINUTES:
                raise StepError(f"Wait time for '{name}' must be between 1 and {MAX_WAIT_MINUTES} minutes")
        out.append({"name": name, "wait_minutes": wait})
    if out:
        out[0]["wait_minutes"] = None   # nothing precedes step 1
    return out


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _template_rows(panel_id: Optional[int], session: Session) -> List[PanelProcessStep]:
    q = select(PanelProcessStep)
    q = q.where(PanelProcessStep.panel_id == panel_id) if panel_id is not None \
        else q.where(PanelProcessStep.panel_id == None)  # noqa: E711
    return sorted(session.exec(q).all(), key=lambda r: r.seq)


def template_steps(panel_id: Optional[int], session: Session) -> Tuple[List[dict], str]:
    """([{name, wait_minutes}], source) — source is 'panel' | 'lab_default' | 'built_in'."""
    if panel_id is not None:
        rows = _template_rows(panel_id, session)
        if rows:
            return [{"name": r.name, "wait_minutes": r.wait_minutes} for r in rows], "panel"
    rows = _template_rows(None, session)
    if rows:
        return [{"name": r.name, "wait_minutes": r.wait_minutes} for r in rows], "lab_default"
    return [{"name": n, "wait_minutes": None} for n in DEFAULT_STEPS], "built_in"


def template_for_panel(panel_id: Optional[int], session: Session) -> Tuple[List[str], str]:
    """(step names, source)."""
    steps, source = template_steps(panel_id, session)
    return [s["name"] for s in steps], source


def set_template(panel_id: Optional[int], steps, session: Session) -> List[dict]:
    """Replace a panel's (or the lab default's) steps. Accepts names or
    {name, wait_minutes} dicts. Empty = remove the panel override."""
    clean = _clean_steps(steps)
    for r in _template_rows(panel_id, session):
        session.delete(r)
    if not clean:
        return []
    if len(clean) < 2:
        raise StepError("At least two steps are needed: cocktail added, and a final step")
    if len(clean) > MAX_STEPS:
        raise StepError(f"At most {MAX_STEPS} steps")
    for i, st in enumerate(clean, start=1):
        session.add(PanelProcessStep(panel_id=panel_id, seq=i, name=st["name"], wait_minutes=st["wait_minutes"]))
    return clean


def apply_timers_to_live_tubes(session: Session) -> int:
    """Push the current templates' wait times onto samples still on the board.

    Step NAMES and ORDER stay frozen per tube (so editing a panel can't reshuffle
    a sample mid-processing), but timers are expected to take effect at once: a
    lab that adds a 15-minute incubation wants to see it on the tubes already
    being stained. Only steps not yet done are touched, matched by name.
    Returns the number of tubes changed.
    """
    from sqlmodel import col
    live_orders = session.exec(
        select(SampleOrder.id).where(col(SampleOrder.status).in_(("in_queue", "in_processing")))
    ).all()
    if not live_orders:
        return 0
    tubes = session.exec(
        select(SampleOrderTube).where(col(SampleOrderTube.sample_order_id).in_(live_orders))
    ).all()
    cache: Dict[Optional[int], Dict[str, Optional[int]]] = {}
    changed = 0
    for t in tubes:
        if t.panel_id not in cache:
            steps, _ = template_steps(t.panel_id, session)
            cache[t.panel_id] = {s["name"].strip().lower(): s["wait_minutes"] for s in steps}
        waits = cache[t.panel_id]
        touched = False
        for st in tube_steps(t, session):
            if st.completed_at is not None or st.seq == 1:
                continue
            key = st.name.strip().lower()
            if key in waits and st.wait_minutes != waits[key]:
                st.wait_minutes = waits[key]
                session.add(st)
                touched = True
        changed += touched
    return changed


# ---------------------------------------------------------------------------
# Per-tube steps
# ---------------------------------------------------------------------------

def tube_steps(tube: SampleOrderTube, session: Session) -> List[SampleOrderTubeStep]:
    return sorted(
        session.exec(select(SampleOrderTubeStep).where(SampleOrderTubeStep.tube_id == tube.id)).all(),
        key=lambda s: s.seq,
    )


def ensure_tube_steps(tube: SampleOrderTube, session: Session,
                      order: Optional[SampleOrder] = None) -> List[SampleOrderTubeStep]:
    """Create the tube's step copy if missing. Tubes that pre-date this feature
    are back-filled consistently with their state: a consumed tube has step 1
    done; a tube on a completed order has every step done."""
    steps = tube_steps(tube, session)
    if steps:
        return steps
    order = order or session.get(SampleOrder, tube.sample_order_id)
    tmpl, _ = template_steps(tube.panel_id, session)
    created = []
    for i, t in enumerate(tmpl, start=1):
        st = SampleOrderTubeStep(tube_id=tube.id, seq=i, name=t["name"], wait_minutes=t["wait_minutes"])
        if order and order.status == "completed":
            st.completed_at = order.completed_at or order.processing_started_at or datetime.now()
        elif i == 1 and tube.status == "consumed":
            st.completed_at = (order.processing_started_at if order else None) or datetime.now()
        session.add(st)
        created.append(st)
    session.flush()
    return created


def next_step(steps: List[SampleOrderTubeStep]) -> Optional[SampleOrderTubeStep]:
    return next((s for s in steps if s.completed_at is None), None)


def last_done(steps: List[SampleOrderTubeStep]) -> Optional[SampleOrderTubeStep]:
    done = [s for s in steps if s.completed_at is not None]
    return done[-1] if done else None


def ready_at(steps: List[SampleOrderTubeStep], step: SampleOrderTubeStep) -> Optional[datetime]:
    """When `step` becomes due: previous step's completion + wait. None if no timer
    or the previous step isn't done yet."""
    if not step.wait_minutes or step.seq <= 1:
        return None
    prev = next((s for s in steps if s.seq == step.seq - 1), None)
    if not prev or not prev.completed_at:
        return None
    return prev.completed_at + timedelta(minutes=step.wait_minutes)


def can_undo(step: Optional[SampleOrderTubeStep], now: Optional[datetime] = None) -> bool:
    return bool(step and step.completed_at and (now or datetime.now()) - step.completed_at <= UNDO_WINDOW)


# ---------------------------------------------------------------------------
# Cocktail consumption for a single tube
# ---------------------------------------------------------------------------

def consume_tube(tube: SampleOrderTube, order: SampleOrder, user_id: int, session: Session) -> CocktailUsageLog:
    if tube.status != "reserved" or not tube.reserved_cocktail_id:
        raise StepError("Tube has no reserved cocktail test")
    cocktail = session.get(Cocktail, tube.reserved_cocktail_id)
    if not cocktail:
        raise StepError("Reserved cocktail no longer exists")
    cocktail.reserved_tests = max(0, (cocktail.reserved_tests or 0) - 1)
    cocktail.remaining_tests = max(0, cocktail.remaining_tests - 1)
    if cocktail.remaining_tests <= 0:
        cocktail.remaining_tests = 0
        cocktail.active = False
    usage = CocktailUsageLog(
        cocktail_id=cocktail.id,
        sample_order_tube_id=tube.id,
        test_date=date.today(),
        count=1,
        entered_by=user_id,
        notes=f"Sample order #{order.id} ({order.lab_id})",
    )
    tube.status = "consumed"
    session.add(cocktail)
    session.add(usage)
    session.add(tube)
    return usage


def unconsume_tube(tube: SampleOrderTube, session: Session) -> None:
    """Exact reversal of consume_tube: the test goes back to being reserved."""
    if tube.status != "consumed" or not tube.reserved_cocktail_id:
        return
    logs = session.exec(
        select(CocktailUsageLog).where(CocktailUsageLog.sample_order_tube_id == tube.id)
    ).all()
    if not logs:
        raise StepError("This tube's cocktail use pre-dates step tracking and can't be reversed here")
    cocktail = session.get(Cocktail, tube.reserved_cocktail_id)
    for log in logs:
        session.delete(log)
    if cocktail:
        cocktail.remaining_tests += 1
        cocktail.reserved_tests = (cocktail.reserved_tests or 0) + 1
        if cocktail.expiry_date is None or cocktail.expiry_date >= date.today():
            cocktail.active = True
        session.add(cocktail)
    tube.status = "reserved"
    session.add(tube)


# ---------------------------------------------------------------------------
# Complete / undo
# ---------------------------------------------------------------------------

def _live_tubes(order: SampleOrder, session: Session) -> List[SampleOrderTube]:
    return session.exec(select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)).all()


def _order_all_done(order: SampleOrder, session: Session) -> bool:
    for t in _live_tubes(order, session):
        if next_step(ensure_tube_steps(t, session, order)) is not None:
            return False
    return True


def complete_step(
    tube: SampleOrderTube,
    seq: int,
    *,
    user_id: int,
    session: Session,
    staff_id: Optional[int] = None,
    force: bool = False,
) -> SampleOrderTubeStep:
    order = session.get(SampleOrder, tube.sample_order_id)
    if not order or order.status not in ("in_queue", "in_processing"):
        raise StepError(f"Order is {order.status if order else 'missing'} — steps can't be changed")

    steps = ensure_tube_steps(tube, session, order)
    nxt = next_step(steps)
    if nxt is None:
        raise StepError("All steps for this tube are already done")
    if nxt.seq != seq:
        raise StepError(f"Next step for this tube is '{nxt.name}' (step {nxt.seq}), not step {seq}")

    now = datetime.now()
    due = ready_at(steps, nxt)
    early = int((due - now).total_seconds()) if due and due > now else 0
    if early > 0 and not force:
        raise TimerNotElapsed(nxt.name, early)

    if seq == 1:
        if tube.status == "awaiting_cocktail":
            # A cocktail may have been prepared since the order was queued
            from app.services.sample_orders import reserve_tube
            if reserve_tube(tube, session) is None:
                raise StepError("No cocktail available for this tube — prepare one first")
        if tube.status == "reserved":
            consume_tube(tube, order, user_id, session)
        if order.status == "in_queue":
            order.status = "in_processing"
            order.processing_started_at = now
        if staff_id and not order.processing_technologist_id:
            order.processing_technologist_id = staff_id
        session.add(order)

    nxt.completed_at = now
    nxt.completed_by_staff_id = staff_id
    nxt.completed_by_user_id = user_id
    nxt.completed_early_seconds = early or None
    session.add(nxt)
    session.flush()

    if _order_all_done(order, session):
        order.status = "completed"
        order.completed_at = now
        session.add(order)
    return nxt


def undo_step(tube: SampleOrderTube, seq: int, session: Session) -> SampleOrderTubeStep:
    order = session.get(SampleOrder, tube.sample_order_id)
    if not order or order.status == "cancelled":
        raise StepError("Order is cancelled — steps can't be changed")
    steps = ensure_tube_steps(tube, session, order)
    last = last_done(steps)
    if last is None or last.seq != seq:
        raise StepError("Only the most recent step of a tube can be undone")
    if not can_undo(last):
        raise StepError(f"Undo is only allowed within {int(UNDO_WINDOW.total_seconds() // 60)} minutes")

    if order.status == "completed":
        order.status = "in_processing"
        order.completed_at = None
    if seq == 1:
        unconsume_tube(tube, session)
    last.completed_at = None
    last.completed_by_staff_id = None
    last.completed_by_user_id = None
    last.completed_early_seconds = None
    session.add(last)
    session.flush()

    if seq == 1:
        started = any(
            s.completed_at for t in _live_tubes(order, session)
            for s in ensure_tube_steps(t, session, order)
        )
        if not started:
            order.status = "in_queue"
            order.processing_started_at = None
    session.add(order)
    return last


def step_progress(tube: SampleOrderTube, session: Session) -> Dict[str, object]:
    steps = ensure_tube_steps(tube, session)
    nxt = next_step(steps)
    return {
        "steps_total": len(steps),
        "steps_done": sum(1 for s in steps if s.completed_at),
        "current_step": nxt.name if nxt else None,
    }
