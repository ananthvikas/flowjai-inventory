"""
services/cocktails.py — the single cocktail service.

This module replaces BOTH of the previous parallel implementations:
    services/cocktail.py   (preflight_check / prepare_cocktail / use_cocktail_tests)
    services/cocktails.py  (simulate / prepare / use_cocktail)

They implemented the same two-phase workflow with different semantics — only
one of them set cocktail_code, and each carried its own copy of the FIFO
deduction loop. Delete services/cocktail.py and use this file.

Public API:
    simulate(...)      dry run: stock impact and warnings, no DB writes
    prepare(...)       commits FIFO deductions and creates the Cocktail record
    use_cocktail(...)  decrements remaining_tests when tests are logged

Legacy aliases preflight_check / prepare_cocktail / use_cocktail_tests are kept
so existing imports of services.cocktail keep resolving after the delete.

FIFO deduction is delegated to services.consumption.record_cocktail_consumption
— there is now exactly one implementation of lot deduction in the codebase.

NOTE ON CONSISTENCY: the simulation estimates days-remaining from the mean of
recent daily consumption, whereas the alert pipeline uses the Holt ETS forecast.
The mean is used here because _max_safe_tests evaluates the estimate O(log n)
times per antibody and the ETS grid search is far too slow for that loop. The
two can therefore differ by a few days on trending series; the simulation is a
guard rail, the alert is the reportable figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlmodel import Session, select

from app.models import (
    AlertRule,
    Antibody,
    Cocktail,
    Fluorochrome,
    Panel,
    PanelComponent,
    StockLot,
)
from app.services.consumption import record_cocktail_consumption

DEFAULT_ALERT_THRESHOLD_DAYS = 42
MAX_SIMULATED_TESTS = 500


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class AffectedPanel:
    panel_id: int
    panel_name: str
    test_code: str


@dataclass
class AntibodyImpact:
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    vendor: Optional[str]
    volume_to_deduct_ul: float
    current_stock_ul: float
    stock_after_ul: float
    days_remaining_before: Optional[float]
    days_remaining_after: Optional[float]
    below_threshold: bool
    shortfall_ul: float
    affected_panels: List[AffectedPanel] = field(default_factory=list)


@dataclass
class SimulationResult:
    panel_id: int
    panel_name: str
    test_count: int
    impacts: List[AntibodyImpact]
    has_warnings: bool
    has_shortfall: bool
    max_safe_tests: Optional[int]
    warnings: List[str]


@dataclass
class CocktailShortfall:
    antibody_id: int
    antibody_name: str
    requested_ul: float
    shortfall_ul: float

    def describe(self) -> str:
        return (
            f"{self.antibody_name}: needed {self.requested_ul:.1f} µl, "
            f"short by {self.shortfall_ul:.1f} µl (stock now recorded as exhausted)"
        )


@dataclass
class PrepareResult:
    cocktail: Cocktail
    shortfalls: List[CocktailShortfall] = field(default_factory=list)

    @property
    def had_shortfall(self) -> bool:
        return bool(self.shortfalls)


# ---------------------------------------------------------------------------
# Internal helpers (cached per call to keep the binary search cheap)
# ---------------------------------------------------------------------------

class _Cache:
    """Per-simulation cache so _max_safe_tests doesn't re-query on every probe."""

    def __init__(self, session: Session):
        self.session = session
        self._stock: Dict[int, float] = {}
        self._avg: Dict[int, float] = {}
        self._threshold: Dict[int, int] = {}

    def stock(self, antibody_id: int) -> float:
        if antibody_id not in self._stock:
            lots = self.session.exec(
                select(StockLot)
                .where(StockLot.antibody_id == antibody_id)
                .where(StockLot.active == True)      # noqa: E712
            ).all()
            self._stock[antibody_id] = round(sum(l.current_volume_ul for l in lots), 3)
        return self._stock[antibody_id]

    def avg_daily(self, antibody_id: int) -> float:
        if antibody_id not in self._avg:
            try:
                from app.services.forecast import _get_daily_consumption
                daily = _get_daily_consumption(antibody_id, self.session, history_days=60)
                self._avg[antibody_id] = float(daily.mean()) if len(daily) > 0 else 0.0
            except Exception:
                self._avg[antibody_id] = 0.0
        return self._avg[antibody_id]

    def threshold_days(self, antibody_id: int) -> int:
        if antibody_id not in self._threshold:
            rule = self.session.exec(
                select(AlertRule).where(AlertRule.antibody_id == antibody_id)
            ).first()
            self._threshold[antibody_id] = (
                rule.alert_threshold_days if rule else DEFAULT_ALERT_THRESHOLD_DAYS
            )
        return self._threshold[antibody_id]


def _days_left(stock_ul: float, avg_daily: float) -> Optional[float]:
    if avg_daily <= 0:
        return None
    return round(stock_ul / avg_daily, 1)


def _other_panels(antibody_id: int, exclude_panel_id: int, session: Session) -> List[AffectedPanel]:
    comps = session.exec(
        select(PanelComponent)
        .where(PanelComponent.antibody_id == antibody_id)
        .where(PanelComponent.panel_id != exclude_panel_id)
    ).all()
    result, seen = [], set()
    for c in comps:
        if c.panel_id in seen:
            continue
        seen.add(c.panel_id)
        p = session.get(Panel, c.panel_id)
        if p and p.active:
            result.append(AffectedPanel(panel_id=p.id, panel_name=p.name, test_code=p.test_code))
    return result


def _max_safe_tests(components: List[PanelComponent], cache: _Cache) -> int:
    """Largest test count that triggers no warning, by binary search."""

    def safe(n: int) -> bool:
        for comp in components:
            after = cache.stock(comp.antibody_id) - comp.ul_per_test() * n
            if after < 0:
                return False
            days = _days_left(after, cache.avg_daily(comp.antibody_id))
            if days is not None and days < cache.threshold_days(comp.antibody_id):
                return False
        return True

    if not safe(1):
        return 0
    lo, hi = 1, MAX_SIMULATED_TESTS
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if safe(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


# ---------------------------------------------------------------------------
# Phase 1 — simulation (no writes)
# ---------------------------------------------------------------------------

def simulate(panel_id: int, test_count: int, session: Session) -> SimulationResult:
    panel = session.get(Panel, panel_id)
    if not panel:
        raise ValueError(f"Panel {panel_id} not found")
    if test_count <= 0:
        raise ValueError("test_count must be > 0")

    components = session.exec(
        select(PanelComponent).where(PanelComponent.panel_id == panel_id)
    ).all()

    cache = _Cache(session)
    impacts: List[AntibodyImpact] = []
    warnings: List[str] = []
    has_warnings = False
    has_shortfall = False

    for comp in components:
        ab = session.get(Antibody, comp.antibody_id)
        if not ab:
            continue
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None

        vol = round(comp.ul_per_test() * test_count, 3)
        stock_now = cache.stock(comp.antibody_id)
        stock_after = round(stock_now - vol, 3)
        avg = cache.avg_daily(comp.antibody_id)
        thr = cache.threshold_days(comp.antibody_id)

        days_before = _days_left(stock_now, avg)
        days_after = _days_left(max(stock_after, 0), avg)
        shortfall = round(max(0.0, -stock_after), 3)

        below = shortfall > 0 or (days_after is not None and days_after < thr)
        if below:
            has_warnings = True
        if shortfall > 0:
            has_shortfall = True

        affected = _other_panels(comp.antibody_id, panel_id, session) if below else []

        if below:
            others = ", ".join(p.test_code for p in affected) if affected else "no other panels"
            if shortfall > 0:
                warnings.append(
                    f"{ab.name}: insufficient stock (need {vol:.0f} µl, "
                    f"have {stock_now:.0f} µl, shortfall {shortfall:.0f} µl). "
                    f"Also used in: {others}."
                )
            else:
                warnings.append(
                    f"{ab.name}: only {days_after:.0f} days remaining after deduction "
                    f"(threshold {thr} days). Also used in: {others}."
                )

        impacts.append(AntibodyImpact(
            antibody_id=comp.antibody_id,
            antibody_name=ab.name,
            fluorochrome=fc.name if fc else None,
            vendor=ab.vendor,
            volume_to_deduct_ul=vol,
            current_stock_ul=stock_now,
            stock_after_ul=max(stock_after, 0),
            days_remaining_before=days_before,
            days_remaining_after=days_after,
            below_threshold=below,
            shortfall_ul=shortfall,
            affected_panels=affected,
        ))

    max_safe = _max_safe_tests(components, cache) if has_warnings else None

    return SimulationResult(
        panel_id=panel_id,
        panel_name=panel.name,
        test_count=test_count,
        impacts=impacts,
        has_warnings=has_warnings,
        has_shortfall=has_shortfall,
        max_safe_tests=max_safe,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Phase 2 — preparation (writes)
# ---------------------------------------------------------------------------

def prepare(
    panel_id: int,
    test_count: int,
    prepared_date: date,
    prepared_by_user_id: int,
    session: Session,
    expiry_date: Optional[date] = None,
    lot_notes: Optional[str] = None,
    prepared_by_staff_id: Optional[int] = None,
) -> PrepareResult:
    """
    Deduct stock FIFO and create the Cocktail record.

    Every component is deducted regardless of whether an earlier one was short —
    same contract as test-log consumption. Shortfalls are returned rather than
    raised, because the technologist has already confirmed the mix at this point
    and the cocktail physically exists.
    """
    panel = session.get(Panel, panel_id)
    if not panel:
        raise ValueError(f"Panel {panel_id} not found")
    if test_count <= 0:
        raise ValueError("test_count must be > 0")

    components = session.exec(
        select(PanelComponent).where(PanelComponent.panel_id == panel_id)
    ).all()
    if not components:
        raise ValueError(f"Panel {panel.name} has no components to mix")

    # Human-readable cocktail code: <test_code>_<YYYYMMDD>_<HHMMSS>
    # Two preps of the same panel in the same second (double-click, batch prep)
    # used to collide on the unique index and 500 — disambiguate with a suffix.
    base_code = f"{panel.test_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cocktail_code, n = base_code, 1
    while session.exec(select(Cocktail).where(Cocktail.cocktail_code == cocktail_code)).first():
        n += 1
        cocktail_code = f"{base_code}_{n}"

    cocktail = Cocktail(
        cocktail_code=cocktail_code,
        panel_id=panel_id,
        prepared_by=prepared_by_user_id,
        prepared_by_staff_id=prepared_by_staff_id,
        prepared_date=prepared_date,
        total_tests=test_count,
        remaining_tests=test_count,
        reserved_tests=0,
        expiry_date=expiry_date,
        lot_notes=lot_notes,
        active=True,
    )
    session.add(cocktail)
    session.flush()

    shortfalls: List[CocktailShortfall] = []
    for comp in components:
        total_ul = round(comp.ul_per_test() * test_count, 3)
        _, remaining = record_cocktail_consumption(
            cocktail_id=cocktail.id,
            antibody_id=comp.antibody_id,
            total_ul=total_ul,
            session=session,
        )
        if remaining > 0:
            ab = session.get(Antibody, comp.antibody_id)
            shortfalls.append(CocktailShortfall(
                antibody_id=comp.antibody_id,
                antibody_name=ab.name if ab else f"id={comp.antibody_id}",
                requested_ul=total_ul,
                shortfall_ul=round(remaining, 3),
            ))

    if shortfalls:
        note = "[STOCK SHORTFALL] " + "; ".join(s.describe() for s in shortfalls)
        cocktail.lot_notes = ((cocktail.lot_notes or "") + " " + note).strip()[:256]
        session.add(cocktail)

    return PrepareResult(cocktail=cocktail, shortfalls=shortfalls)


def use_cocktail(cocktail_id: int, test_count: int, session: Session) -> Cocktail:
    """
    Decrement remaining_tests. No antibody stock deduction — that happened at
    preparation. Refuses to consume tests that are held by a worklist
    reservation, since available = remaining - reserved.
    """
    cocktail = session.get(Cocktail, cocktail_id)
    if not cocktail:
        raise ValueError(f"Cocktail {cocktail_id} not found")
    if not cocktail.active:
        raise ValueError("Cocktail is exhausted or inactive")
    if test_count <= 0:
        raise ValueError("test_count must be > 0")

    available = cocktail.remaining_tests - (cocktail.reserved_tests or 0)
    if test_count > available:
        raise ValueError(
            f"Only {available} test(s) available in this cocktail "
            f"({cocktail.remaining_tests} remaining, "
            f"{cocktail.reserved_tests or 0} reserved for queued orders)"
        )

    cocktail.remaining_tests -= test_count
    if cocktail.remaining_tests <= 0:
        cocktail.remaining_tests = 0
        cocktail.active = False
    session.add(cocktail)
    return cocktail


def prepared_by_name(cocktail: Cocktail, session: Session) -> Optional[str]:
    """Name of the person who mixed the cocktail. Falls back to the login
    username for cocktails recorded before staff names were captured."""
    from app.models import Staff, User
    if cocktail.prepared_by_staff_id:
        s = session.get(Staff, cocktail.prepared_by_staff_id)
        if s:
            return s.name
    u = session.get(User, cocktail.prepared_by)
    return u.username if u else None


# ---------------------------------------------------------------------------
# Legacy aliases — keep imports of the deleted services/cocktail.py resolving
# ---------------------------------------------------------------------------

preflight_check = simulate
prepare_cocktail = prepare
use_cocktail_tests = use_cocktail
