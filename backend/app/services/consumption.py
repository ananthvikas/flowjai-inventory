"""
services/consumption.py

FIFO stock deduction for test logs and cocktail preparation, plus physical
verification of residual lot volume.

CONSUMPTION CONTRACT (revised):
    record_consumption() deducts EVERY panel component before reporting any
    shortfall.

    The previous implementation raised InsufficientStockError from inside the
    component loop. Because routers/tests.py catches that exception, converts
    it to a warning and then commits, every component after the first short
    antibody was silently never deducted. Stock for those antibodies stayed
    inflated indefinitely, which then propagated into the depletion forecast
    and into the verification deltas used for agreement analysis.

    The contract is now:
      1. Every component is processed. All available volume is deducted.
      2. A lot is never driven below zero; the un-deducted remainder is
         returned as a Shortfall.
      3. If any shortfalls occurred, InsufficientStockError is raised AFTER
         all deductions, carrying the complete list. The caller may safely
         commit — the deductions already in the session are correct and
         complete for the stock that existed.

VERIFICATION CONTRACT (revised):
    verify_stock_volume() now ALWAYS writes a VerificationLog and requires the
    verifying user id. Previously the log was written only when a user id was
    supplied, while current_volume_ul was corrected unconditionally — any call
    path that omitted the user silently destroyed the evidence while still
    moving the number.

    Measurement method and its resolution are recorded so the reference
    uncertainty can be reported honestly in Bland-Altman analysis. The
    physical measurement is itself an estimate.

This module is deliberately decoupled from FastAPI — it takes a Session and
model instances.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple

from sqlmodel import Session, select

from app.models import (
    Antibody,
    ConsumptionLog,
    PanelComponent,
    StockLot,
    TestLog,
    VerificationLog,
)

VALID_MEASUREMENT_METHODS = ("pipette", "gravimetric")


# ---------------------------------------------------------------------------
# Shortfall reporting
# ---------------------------------------------------------------------------

@dataclass
class Shortfall:
    """One antibody whose available stock could not cover the requested volume."""
    antibody_id: int
    antibody_name: str
    requested_ul: float
    deducted_ul: float
    shortfall_ul: float

    def describe(self) -> str:
        return (
            f"{self.antibody_name}: needed {self.requested_ul:.1f} µl, "
            f"only {self.deducted_ul:.1f} µl available "
            f"(short by {self.shortfall_ul:.1f} µl — stock now recorded as exhausted)"
        )


class InsufficientStockError(Exception):
    """
    Raised after a consumption run in which one or more antibodies could not be
    fully covered. All possible deductions have already been applied to the
    session by the time this is raised.
    """

    def __init__(self, shortfalls: List[Shortfall]):
        self.shortfalls = shortfalls
        super().__init__("; ".join(s.describe() for s in shortfalls))

    # --- convenience accessors (kept so older call sites keep working) ---

    @property
    def antibody_id(self) -> Optional[int]:
        return self.shortfalls[0].antibody_id if self.shortfalls else None

    @property
    def antibody_name(self) -> Optional[str]:
        return self.shortfalls[0].antibody_name if self.shortfalls else None

    @property
    def shortfall_ul(self) -> float:
        return sum(s.shortfall_ul for s in self.shortfalls)

    def messages(self) -> List[str]:
        return [s.describe() for s in self.shortfalls]


# ---------------------------------------------------------------------------
# Test log consumption
# ---------------------------------------------------------------------------

def record_consumption(test_log: TestLog, session: Session) -> List[ConsumptionLog]:
    """
    Deduct every antibody in the panel for this test log, FIFO across lots.

    Call after flushing test_log but before committing. Returns all
    ConsumptionLog rows created (already added to the session).

    Raises InsufficientStockError only after ALL components have been
    processed. The exception carries every shortfall; the deductions that were
    possible are already in the session and should be committed.
    """
    components: List[PanelComponent] = session.exec(
        select(PanelComponent).where(PanelComponent.panel_id == test_log.panel_id)
    ).all()

    created_logs: List[ConsumptionLog] = []
    shortfalls: List[Shortfall] = []

    for component in components:
        total_needed_ul = round(component.ul_per_test() * test_log.count, 3)

        logs, remaining = _deduct_from_lots(
            antibody_id=component.antibody_id,
            total_ul=total_needed_ul,
            test_log=test_log,
            session=session,
        )
        created_logs.extend(logs)

        if remaining > 0:
            antibody = session.get(Antibody, component.antibody_id)
            shortfalls.append(Shortfall(
                antibody_id=component.antibody_id,
                antibody_name=antibody.name if antibody else f"id={component.antibody_id}",
                requested_ul=total_needed_ul,
                deducted_ul=round(total_needed_ul - remaining, 3),
                shortfall_ul=round(remaining, 3),
            ))

    # Every component has now been processed. Report shortfalls once.
    if shortfalls:
        raise InsufficientStockError(shortfalls)

    return created_logs


def _deduct_from_lots(
    antibody_id: int,
    total_ul: float,
    test_log: Optional[TestLog],
    session: Session,
) -> Tuple[List[ConsumptionLog], float]:
    """
    FIFO deduction across active lots (oldest date_received first).
    Returns (logs_created, remaining_shortfall).
    remaining_shortfall == 0 means the volume was fully covered.
    A lot is never driven below zero.
    """
    lots: List[StockLot] = session.exec(
        select(StockLot)
        .where(StockLot.antibody_id == antibody_id)
        .where(StockLot.active == True)          # noqa: E712
        .where(StockLot.current_volume_ul > 0)
        .order_by(StockLot.date_received)        # FIFO
    ).all()

    remaining = round(total_ul, 3)
    logs: List[ConsumptionLog] = []

    for lot in lots:
        if remaining <= 0:
            break

        can_take = min(lot.current_volume_ul, remaining)
        lot.current_volume_ul = round(lot.current_volume_ul - can_take, 3)

        if lot.current_volume_ul <= 0:
            lot.current_volume_ul = 0.0
            lot.active = False  # mark exhausted

        log = ConsumptionLog(
            test_log_id=test_log.id if test_log is not None else None,
            antibody_id=antibody_id,
            stock_lot_id=lot.id,
            volume_consumed_ul=round(can_take, 3),
            timestamp=datetime.now(),
        )
        session.add(lot)
        session.add(log)
        logs.append(log)
        remaining = round(remaining - can_take, 3)

    return logs, max(remaining, 0.0)


# ---------------------------------------------------------------------------
# Cocktail consumption
# ---------------------------------------------------------------------------

def record_cocktail_consumption(
    cocktail_id: int,
    antibody_id: int,
    total_ul: float,
    session: Session,
) -> Tuple[List[ConsumptionLog], float]:
    """
    Deduct total_ul from stock lots (FIFO) for a cocktail mixing event.
    Returns (logs_created, remaining_shortfall).
    ConsumptionLog rows are linked to cocktail_id rather than a test_log.

    This is the single FIFO implementation used for cocktails; the previous
    duplicate loop in services/cocktails.py has been removed.
    """
    lots: List[StockLot] = session.exec(
        select(StockLot)
        .where(StockLot.antibody_id == antibody_id)
        .where(StockLot.active == True)          # noqa: E712
        .where(StockLot.current_volume_ul > 0)
        .order_by(StockLot.date_received)
    ).all()

    remaining = round(total_ul, 3)
    logs: List[ConsumptionLog] = []

    for lot in lots:
        if remaining <= 0:
            break

        can_take = min(lot.current_volume_ul, remaining)
        lot.current_volume_ul = round(lot.current_volume_ul - can_take, 3)

        if lot.current_volume_ul <= 0:
            lot.current_volume_ul = 0.0
            lot.active = False

        log = ConsumptionLog(
            test_log_id=None,
            cocktail_id=cocktail_id,
            antibody_id=antibody_id,
            stock_lot_id=lot.id,
            volume_consumed_ul=round(can_take, 3),
            timestamp=datetime.now(),
        )
        session.add(lot)
        session.add(log)
        logs.append(log)
        remaining = round(remaining - can_take, 3)

    return logs, max(remaining, 0.0)


# ---------------------------------------------------------------------------
# Physical verification
# ---------------------------------------------------------------------------

def verify_stock_volume(
    lot: StockLot,
    verified_volume_ul: float,
    session: Session,
    verified_by_user_id: int,
    measurement_method: str = "pipette",
    pipette_increment_ul: Optional[float] = None,
    verification_cycle: Optional[str] = None,
    verification_date: Optional[date] = None,
) -> VerificationLog:
    """
    Record a physical verification of a lot's residual volume and correct the
    running estimate.

    A VerificationLog is ALWAYS written — this is the primary dataset for
    agreement reporting, so a verification must never silently move the stock
    figure without leaving evidence.

    Args:
        verified_by_user_id: required. Who performed the measurement.
        measurement_method: "pipette" or "gravimetric".
        pipette_increment_ul: resolution floor of the measurement (e.g. 5.0 for
            a 5 µl-increment pipette). Needed to state the reference
            uncertainty in Bland-Altman analysis.
        verification_cycle: label grouping verifications performed together
            (e.g. a prep batch). Distinct cycles, not raw point count, drive
            the statistical strength of the dataset.

    Returns the VerificationLog that was written.

    Raises ValueError if the user id is missing or the method is unrecognised —
    fail loudly rather than discard a data point.
    """
    if verified_by_user_id is None:
        raise ValueError(
            "verified_by_user_id is required — a verification cannot be recorded "
            "anonymously because it is a publishable observation."
        )
    if measurement_method not in VALID_MEASUREMENT_METHODS:
        raise ValueError(
            f"measurement_method must be one of {VALID_MEASUREMENT_METHODS}, "
            f"got {measurement_method!r}"
        )
    if verified_volume_ul < 0:
        raise ValueError("verified_volume_ul cannot be negative")

    estimate = lot.current_volume_ul
    delta = round(verified_volume_ul - estimate, 3)
    delta_pct = round(delta / estimate * 100, 2) if estimate else None

    vlog = VerificationLog(
        stock_lot_id=lot.id,
        antibody_id=lot.antibody_id,
        verified_by=verified_by_user_id,
        verification_date=verification_date or date.today(),
        system_estimate_ul=estimate,
        measured_volume_ul=verified_volume_ul,
        delta_ul=delta,
        delta_pct=delta_pct,
        measurement_method=measurement_method,
        pipette_increment_ul=pipette_increment_ul,
        verification_cycle=verification_cycle,
    )
    session.add(vlog)

    lot.last_verified_volume_ul = verified_volume_ul
    lot.last_verified_date = vlog.verification_date
    lot.current_volume_ul = verified_volume_ul
    lot.active = verified_volume_ul > 0
    session.add(lot)

    return vlog


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_total_stock_ul(antibody_id: int, session: Session) -> float:
    """Sum of current_volume_ul across all active lots for an antibody."""
    lots: List[StockLot] = session.exec(
        select(StockLot)
        .where(StockLot.antibody_id == antibody_id)
        .where(StockLot.active == True)          # noqa: E712
    ).all()
    return round(sum(lot.current_volume_ul for lot in lots), 3)
