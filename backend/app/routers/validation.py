"""
routers/validation.py

Validation data export for agreement reporting and publication.

Three datasets:
  1. Volume tracking agreement — system estimate vs physical measurement at each
     verification event. Primary validation dataset for manuscript.
     NOTE: physical measurement (pipette or balance) is itself an estimate with
     its own resolution/uncertainty, so this is an AGREEMENT analysis between two
     methods (Bland-Altman), not accuracy against a gold standard.
  2. Alert effectiveness — shortage alerts raised and whether an order followed.
  3. Usage summary — daily consumption rates per antibody over the tracking period.

All endpoints return JSON (dashboardable) plus a CSV download option.

ACCESS: restricted to "service" role only — not visible to regular admin users.
"""

import csv
import io
import statistics
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.auth import require_service
from app.database import get_session
from app.models import (
    Alert, Antibody, ConsumptionLog, Order,
    StockLot, User, VerificationLog,
)

router = APIRouter(prefix="/api/validation", tags=["validation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VerificationAccuracyRow(BaseModel):
    verification_date: str
    antibody_name: str
    lot_no: str
    system_estimate_ul: float
    measured_volume_ul: float
    delta_ul: float
    delta_pct: Optional[float]
    verified_by: str


class AccuracySummary(BaseModel):
    total_verifications: int
    distinct_cycles: int            # number of distinct verification dates (independent cycles)
    distinct_lots: int              # number of distinct antibody lots verified
    mean_absolute_error_ul: float
    mean_absolute_pct_error: Optional[float]
    mean_signed_bias_ul: float      # mean(estimate - measured); ~0 = random, non-zero = systematic
    sd_of_differences_ul: float     # SD of signed differences
    bland_altman_lower_loa_ul: float  # bias - 1.96*SD
    bland_altman_upper_loa_ul: float  # bias + 1.96*SD
    min_delta_ul: float
    max_delta_ul: float
    median_delta_ul: float
    overestimate_count: int     # system > measured (more common — evaporation/dead volume)
    underestimate_count: int
    exact_count: int            # within ±1 µl
    interpretation: str         # plain-language guidance on feasibility vs validation


class AlertEffectivenessRow(BaseModel):
    antibody_name: str
    alert_date: str
    alert_type: str
    days_remaining_at_alert: Optional[float]
    order_placed_within_14_days: bool
    acknowledged: bool


class UsageSummaryRow(BaseModel):
    antibody_name: str
    fluorochrome: Optional[str]
    vendor: Optional[str]
    tracking_days: int
    total_consumed_ul: float
    avg_daily_ul: float
    peak_daily_ul: float
    lots_exhausted: int


class ValidationReport(BaseModel):
    generated_date: str
    tracking_period_days: int
    verification_accuracy: List[VerificationAccuracyRow]
    accuracy_summary: AccuracySummary
    alert_effectiveness: List[AlertEffectivenessRow]
    usage_summary: List[UsageSummaryRow]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tracking_start(session: Session) -> date:
    """Earliest consumption log date — defines the tracking period."""
    earliest = session.exec(
        select(func.min(ConsumptionLog.timestamp))
    ).first()
    if earliest:
        return earliest.date()
    return date.today() - timedelta(days=90)


def _verification_rows(session: Session) -> List[VerificationAccuracyRow]:
    logs = session.exec(
        select(VerificationLog).order_by(VerificationLog.verification_date.desc())
    ).all()
    rows = []
    for vl in logs:
        lot = session.get(StockLot, vl.stock_lot_id)
        ab = session.get(Antibody, vl.antibody_id)
        user = session.get(User, vl.verified_by)
        rows.append(VerificationAccuracyRow(
            verification_date=str(vl.verification_date),
            antibody_name=ab.name if ab else "unknown",
            lot_no=lot.lot_no if lot else "unknown",
            system_estimate_ul=vl.system_estimate_ul,
            measured_volume_ul=vl.measured_volume_ul,
            delta_ul=vl.delta_ul,
            delta_pct=vl.delta_pct,
            verified_by=user.username if user else "unknown",
        ))
    return rows


def _accuracy_summary(rows: List[VerificationAccuracyRow], session: Session = None) -> AccuracySummary:
    if not rows:
        return AccuracySummary(
            total_verifications=0,
            distinct_cycles=0,
            distinct_lots=0,
            mean_absolute_error_ul=0,
            mean_absolute_pct_error=None,
            mean_signed_bias_ul=0,
            sd_of_differences_ul=0,
            bland_altman_lower_loa_ul=0,
            bland_altman_upper_loa_ul=0,
            min_delta_ul=0,
            max_delta_ul=0,
            median_delta_ul=0,
            overestimate_count=0,
            underestimate_count=0,
            exact_count=0,
            interpretation="No verification events yet. Use the Verify button on physical vial checks to build the accuracy dataset.",
        )

    # delta_ul = measured - estimate (per model). For the manuscript we report
    # signed bias as (estimate - measured), i.e. positive = system reads high.
    deltas = [r.delta_ul for r in rows]
    signed_bias_values = [-d for d in deltas]          # estimate - measured
    abs_errors = [abs(d) for d in deltas]
    pct_errors = [abs(r.delta_pct) for r in rows if r.delta_pct is not None]

    mean_bias = statistics.mean(signed_bias_values)
    sd_diff = statistics.stdev(signed_bias_values) if len(signed_bias_values) > 1 else 0.0

    distinct_cycles = len({r.verification_date for r in rows})
    distinct_lots = len({(r.antibody_name, r.lot_no) for r in rows})

    # Plain-language interpretation: how strong a claim the data currently supports
    n = len(rows)
    if distinct_cycles <= 1:
        interp = (
            f"{n} verification points from a SINGLE cycle ({distinct_lots} lots). "
            "These are not independent observations — treat as proof-of-concept / feasibility, "
            "not validation. Report descriptively (range, median) and state that prospective "
            "validation across independent cycles is ongoing."
        )
    elif distinct_cycles < 4:
        interp = (
            f"{n} points across {distinct_cycles} cycles ({distinct_lots} lots). "
            "Preliminary — sufficient for a proof-of-concept Letter framed as early validation. "
            "Accumulate more cycles before quoting a confidence interval on the MAE."
        )
    else:
        interp = (
            f"{n} points across {distinct_cycles} independent cycles ({distinct_lots} lots). "
            "Approaching a defensible validation dataset. Mean signed bias indicates whether error "
            "is systematic (non-zero) or random pipetting loss (~0); Bland-Altman limits give agreement."
        )

    return AccuracySummary(
        total_verifications=n,
        distinct_cycles=distinct_cycles,
        distinct_lots=distinct_lots,
        mean_absolute_error_ul=round(statistics.mean(abs_errors), 2),
        mean_absolute_pct_error=round(statistics.mean(pct_errors), 2) if pct_errors else None,
        mean_signed_bias_ul=round(mean_bias, 2),
        sd_of_differences_ul=round(sd_diff, 2),
        bland_altman_lower_loa_ul=round(mean_bias - 1.96 * sd_diff, 2),
        bland_altman_upper_loa_ul=round(mean_bias + 1.96 * sd_diff, 2),
        min_delta_ul=round(min(deltas), 2),
        max_delta_ul=round(max(deltas), 2),
        median_delta_ul=round(statistics.median(deltas), 2),
        overestimate_count=sum(1 for d in deltas if d < -1),   # system > measured
        underestimate_count=sum(1 for d in deltas if d > 1),   # system < measured
        exact_count=sum(1 for d in deltas if abs(d) <= 1),
        interpretation=interp,
    )


def _alert_effectiveness(session: Session) -> List[AlertEffectivenessRow]:
    alerts = session.exec(
        select(Alert)
        .where(Alert.alert_type == "shortage")
        .order_by(Alert.triggered_at.desc())
    ).all()

    rows = []
    for alert in alerts:
        ab = session.get(Antibody, alert.antibody_id)
        alert_date = alert.triggered_at.date()

        # Check if an order was placed within 14 days
        order_followed = session.exec(
            select(Order)
            .where(Order.antibody_id == alert.antibody_id)
            .where(Order.order_date >= alert_date)
            .where(Order.order_date <= alert_date + timedelta(days=14))
        ).first()

        rows.append(AlertEffectivenessRow(
            antibody_name=ab.name if ab else "unknown",
            alert_date=str(alert_date),
            alert_type=alert.alert_type,
            days_remaining_at_alert=alert.days_remaining,
            order_placed_within_14_days=order_followed is not None,
            acknowledged=alert.acknowledged_at is not None,
        ))
    return rows


def _usage_summary(session: Session, start_date: date) -> List[UsageSummaryRow]:
    antibodies = session.exec(select(Antibody).where(Antibody.active == True)).all()  # noqa
    rows = []
    tracking_days = (date.today() - start_date).days or 1

    for ab in antibodies:
        logs = session.exec(
            select(ConsumptionLog)
            .where(ConsumptionLog.antibody_id == ab.id)
            .where(ConsumptionLog.timestamp >= start_date)
        ).all()

        if not logs:
            continue

        total_ul = sum(l.volume_consumed_ul for l in logs)

        # Daily totals for peak calculation
        from collections import defaultdict
        daily: dict = defaultdict(float)
        for l in logs:
            daily[l.timestamp.date()] += l.volume_consumed_ul
        peak = max(daily.values()) if daily else 0

        exhausted = session.exec(
            select(StockLot)
            .where(StockLot.antibody_id == ab.id)
            .where(StockLot.active == False)  # noqa
            .where(StockLot.current_volume_ul == 0)
        ).all()

        fluor = ab.fluorochrome.name if ab.fluorochrome else None

        rows.append(UsageSummaryRow(
            antibody_name=ab.name,
            fluorochrome=fluor,
            vendor=ab.vendor,
            tracking_days=tracking_days,
            total_consumed_ul=round(total_ul, 2),
            avg_daily_ul=round(total_ul / tracking_days, 3),
            peak_daily_ul=round(peak, 2),
            lots_exhausted=len(exhausted),
        ))

    return sorted(rows, key=lambda r: r.avg_daily_ul, reverse=True)


# ---------------------------------------------------------------------------
# Endpoints — restricted to "service" role only
# ---------------------------------------------------------------------------

@router.get("/report", response_model=ValidationReport)
def get_validation_report(
    session: Session = Depends(get_session),
    _: User = Depends(require_service),
):
    start = _get_tracking_start(session)
    ver_rows = _verification_rows(session)
    return ValidationReport(
        generated_date=str(date.today()),
        tracking_period_days=(date.today() - start).days,
        verification_accuracy=ver_rows,
        accuracy_summary=_accuracy_summary(ver_rows),
        alert_effectiveness=_alert_effectiveness(session),
        usage_summary=_usage_summary(session, start),
    )


@router.get("/export/accuracy-summary.csv")
def export_accuracy_summary_csv(
    session: Session = Depends(get_session),
    _: User = Depends(require_service),
):
    """Publication-ready accuracy statistics in a single CSV (metric, value)."""
    rows = _verification_rows(session)
    s = _accuracy_summary(rows, session)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["metric", "value", "notes"])
    writer.writerow(["total_verification_points", s.total_verifications, "individual Verify events"])
    writer.writerow(["distinct_cycles", s.distinct_cycles, "independent verification dates — drives statistical strength"])
    writer.writerow(["distinct_lots", s.distinct_lots, "antibody lots covered"])
    writer.writerow(["mean_absolute_error_ul", s.mean_absolute_error_ul, "mean |estimate - measured|"])
    writer.writerow(["mean_absolute_pct_error", s.mean_absolute_pct_error if s.mean_absolute_pct_error is not None else "", "%"])
    writer.writerow(["mean_signed_bias_ul", s.mean_signed_bias_ul, "estimate - measured; ~0 = random pipetting loss, non-zero = systematic"])
    writer.writerow(["sd_of_differences_ul", s.sd_of_differences_ul, "SD of signed differences"])
    writer.writerow(["bland_altman_lower_loa_ul", s.bland_altman_lower_loa_ul, "bias - 1.96*SD"])
    writer.writerow(["bland_altman_upper_loa_ul", s.bland_altman_upper_loa_ul, "bias + 1.96*SD"])
    writer.writerow(["min_delta_ul", s.min_delta_ul, "measured - estimate"])
    writer.writerow(["max_delta_ul", s.max_delta_ul, "measured - estimate"])
    writer.writerow(["median_delta_ul", s.median_delta_ul, "measured - estimate"])
    writer.writerow(["within_1ul_count", s.exact_count, "points within +/-1 ul"])
    writer.writerow(["overestimate_count", s.overestimate_count, "system read high (>1 ul)"])
    writer.writerow(["underestimate_count", s.underestimate_count, "system read low (>1 ul)"])
    writer.writerow(["interpretation", s.interpretation, ""])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=accuracy_summary_stats.csv"},
    )


@router.get("/export/verification-accuracy.csv")
def export_verification_csv(
    session: Session = Depends(get_session),
    _: User = Depends(require_service),
):
    rows = _verification_rows(session)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "verification_date", "antibody_name", "lot_no",
        "system_estimate_ul", "measured_volume_ul",
        "delta_ul", "delta_pct", "verified_by",
    ])
    writer.writeheader()
    for r in rows:
        writer.writerow(r.model_dump())
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=verification_accuracy.csv"},
    )


@router.get("/export/usage-summary.csv")
def export_usage_csv(
    session: Session = Depends(get_session),
    _: User = Depends(require_service),
):
    start = _get_tracking_start(session)
    rows = _usage_summary(session, start)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "antibody_name", "fluorochrome", "vendor", "tracking_days",
        "total_consumed_ul", "avg_daily_ul", "peak_daily_ul", "lots_exhausted",
    ])
    writer.writeheader()
    for r in rows:
        writer.writerow(r.model_dump())
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage_summary.csv"},
    )


@router.get("/export/alert-effectiveness.csv")
def export_alerts_csv(
    session: Session = Depends(get_session),
    _: User = Depends(require_service),
):
    rows = _alert_effectiveness(session)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "antibody_name", "alert_date", "alert_type",
        "days_remaining_at_alert", "order_placed_within_14_days", "acknowledged",
    ])
    writer.writeheader()
    for r in rows:
        writer.writerow(r.model_dump())
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alert_effectiveness.csv"},
    )