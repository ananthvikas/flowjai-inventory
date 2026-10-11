"""
services/sample_orders.py — reservation + consumption logic for the worklist.

A sample order has one or more tubes; each tube == one panel == one cocktail test.
Reservation holds a test from a matching cocktail without physically consuming it.
Consumption (when the order moves to "in processing") converts the held reservation
into a real CocktailUsageLog and decrements the cocktail's remaining tests.

Cocktail accounting:
    available_to_reserve = remaining_tests - reserved_tests
    reserve  -> reserved_tests += 1
    consume  -> reserved_tests -= 1, remaining_tests -= 1, write CocktailUsageLog
    release  -> reserved_tests -= 1   (reservation cancelled before consumption)

This module is deliberately decoupled from FastAPI: it takes a Session and models.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlmodel import Session, select

from app.models import (
    Cocktail, CocktailUsageLog, Panel, SampleOrder, SampleOrderTube,
)


def cocktail_available_tests(cocktail: Cocktail) -> int:
    """Tests in this cocktail not already promised to a reservation."""
    return max(0, cocktail.remaining_tests - (cocktail.reserved_tests or 0))


def _candidate_cocktails(panel_id: int, session: Session) -> List[Cocktail]:
    """
    Active, non-expired cocktails for a panel that have at least one free test,
    ordered so the soonest-expiring usable cocktail is drawn first (minimise waste),
    then oldest prepared.
    """
    today = date.today()
    cocktails = session.exec(
        select(Cocktail)
        .where(Cocktail.panel_id == panel_id)
        .where(Cocktail.active == True)  # noqa: E712
    ).all()
    usable = [
        c for c in cocktails
        if cocktail_available_tests(c) >= 1
        and (c.expiry_date is None or c.expiry_date >= today)
    ]
    # expiry asc (None last), then prepared_date asc
    usable.sort(key=lambda c: (c.expiry_date is None, c.expiry_date or date.max, c.prepared_date, c.id))
    return usable


def reserve_tube(tube: SampleOrderTube, session: Session) -> Optional[Cocktail]:
    """
    Try to hold one cocktail test for this tube. Returns the cocktail used,
    or None if no cocktail had a free test. Idempotent for already-reserved tubes.
    """
    if tube.status in ("reserved", "consumed"):
        return session.get(Cocktail, tube.reserved_cocktail_id) if tube.reserved_cocktail_id else None

    candidates = _candidate_cocktails(tube.panel_id, session)
    if not candidates:
        tube.status = "awaiting_cocktail"
        tube.reserved_cocktail_id = None
        session.add(tube)
        return None

    cocktail = candidates[0]
    cocktail.reserved_tests = (cocktail.reserved_tests or 0) + 1
    tube.reserved_cocktail_id = cocktail.id
    tube.status = "reserved"
    session.add(cocktail)
    session.add(tube)
    return cocktail


def release_tube(tube: SampleOrderTube, session: Session) -> None:
    """Cancel a reservation that has not yet been consumed."""
    if tube.status == "reserved" and tube.reserved_cocktail_id:
        cocktail = session.get(Cocktail, tube.reserved_cocktail_id)
        if cocktail:
            cocktail.reserved_tests = max(0, (cocktail.reserved_tests or 0) - 1)
            session.add(cocktail)
    tube.reserved_cocktail_id = None
    tube.status = "awaiting_cocktail"
    session.add(tube)


def reserve_order(order: SampleOrder, session: Session) -> List[dict]:
    """
    Attempt to reserve every not-yet-reserved tube on an order.
    Returns a list of shortfall descriptors for tubes that could not be reserved:
        [{"panel_id", "panel_name", "test_code", "tubes_short"}]
    aggregated by panel.
    """
    tubes = session.exec(
        select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)
    ).all()

    short_by_panel: dict[int, int] = {}
    for tube in tubes:
        if tube.status in ("reserved", "consumed"):
            continue
        cocktail = reserve_tube(tube, session)
        if cocktail is None:
            short_by_panel[tube.panel_id] = short_by_panel.get(tube.panel_id, 0) + 1

    shortfalls = []
    for panel_id, n in short_by_panel.items():
        panel = session.get(Panel, panel_id)
        shortfalls.append({
            "panel_id": panel_id,
            "panel_name": panel.name if panel else f"panel {panel_id}",
            "test_code": panel.test_code if panel else "",
            "tubes_short": n,
        })
    return shortfalls


def unreserved_tubes(order: SampleOrder, session: Session) -> List[SampleOrderTube]:
    """Tubes still awaiting a cocktail (block move to in_processing)."""
    tubes = session.exec(
        select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)
    ).all()
    return [t for t in tubes if t.status == "awaiting_cocktail"]


def consume_order(order: SampleOrder, user_id: int, session: Session) -> List[CocktailUsageLog]:
    """
    Convert all reserved tubes on an order into real cocktail consumption.
    Writes one CocktailUsageLog per tube (count=1) tagged with the order, decrements
    the cocktail's reserved_tests and remaining_tests, deactivates exhausted cocktails.
    Caller must ensure no tube is still awaiting_cocktail.
    """
    tubes = session.exec(
        select(SampleOrderTube).where(SampleOrderTube.sample_order_id == order.id)
    ).all()

    from app.services.processing import consume_tube
    logs: List[CocktailUsageLog] = []
    for tube in tubes:
        if tube.status != "reserved" or not tube.reserved_cocktail_id:
            continue
        logs.append(consume_tube(tube, order, user_id, session))
    return logs
