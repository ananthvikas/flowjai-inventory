"""
services/forecast.py

Forecasting pipeline for antibody depletion estimation.

Strategy:
  - Pull last N days of daily consumption from ConsumptionLog (default 90 days).
  - If >= 14 data points: fit Holt-Winters double exponential smoothing (additive trend).
  - If < 14 data points: fall back to simple moving average of available data.
  - If 0 data points: return None (no forecast possible yet).

Pure-Python/NumPy implementation — no statsmodels dependency, works on any
Python version including 3.13+.
"""

import os

# Which forecaster to use. The Holt trend model was evaluated against 223
# held-out 30-day forecasts on deployment data and lost to a plain moving
# average (MdAPE 44.4% vs 16.1%). With damping free to vary, the fitted trend
# collapsed to zero in 77% of series — batch cocktail preparation produces
# consumption with no exploitable trend at this horizon.
# "ets" and "auto" are kept so the comparison stays reproducible.
FORECAST_METHOD = os.getenv("FLOWJAI_FORECAST_METHOD", "moving_average")
MIN_OBSERVED_DAYS_FOR_ETS = 30

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlmodel import Session, select

from app.models import ConsumptionLog, StockLot


@dataclass
class ForecastResult:
    antibody_id: int
    current_stock_ul: float
    depletion_date: Optional[date]
    days_remaining: Optional[float]
    avg_daily_ul: float
    forecast_daily_ul: float
    history_days: int
    method: str                          # "ets" | "moving_average" | "insufficient_data"
    store_stock_ul: float = 0.0          # total store vials in µl
    forecast_series: List[Dict] = field(default_factory=list)
    confidence_low: List[Dict] = field(default_factory=list)
    confidence_high: List[Dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure-Python Holt-Winters (double exponential smoothing, additive trend)
# ---------------------------------------------------------------------------

def _holtwinters(y: np.ndarray, alpha: float, beta: float) -> Tuple[np.ndarray, float]:
    """
    Double exponential smoothing (Holt linear trend).
    Returns (fitted_values, residual_std).
    """
    n = len(y)
    level = np.zeros(n)
    trend = np.zeros(n)
    fitted = np.zeros(n)

    # Initialise
    level[0] = y[0]
    trend[0] = y[1] - y[0] if n > 1 else 0.0

    for t in range(1, n):
        level[t] = alpha * y[t] + (1 - alpha) * (level[t - 1] + trend[t - 1])
        trend[t] = beta * (level[t] - level[t - 1]) + (1 - beta) * trend[t - 1]
        fitted[t] = level[t - 1] + trend[t - 1]

    residuals = y[1:] - fitted[1:]
    resid_std = float(np.std(residuals)) if len(residuals) > 1 else 0.0
    return fitted, resid_std, level[-1], trend[-1]


def _optimise_holtwinters(y: np.ndarray) -> Tuple[float, float, float, float, float]:
    """
    Grid search over alpha and beta to minimise SSE on the training series.
    Returns (alpha, beta, final_level, final_trend, resid_std).
    """
    best_sse = float("inf")
    best_alpha, best_beta = 0.3, 0.1
    best_level, best_trend, best_std = y[-1], 0.0, 0.0

    for alpha in np.arange(0.1, 1.0, 0.1):
        for beta in np.arange(0.05, 0.5, 0.05):
            fitted, resid_std, final_level, final_trend = _holtwinters(y, alpha, beta)
            sse = float(np.sum((y[1:] - fitted[1:]) ** 2))
            if sse < best_sse:
                best_sse = sse
                best_alpha, best_beta = alpha, beta
                best_level, best_trend, best_std = final_level, final_trend, resid_std

    return best_alpha, best_beta, best_level, best_trend, best_std


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def forecast_antibody(
    antibody_id: int,
    session: Session,
    history_days: int = 90,
    forecast_horizon_days: int = 60,
    current_stock_ul: Optional[float] = None,
) -> ForecastResult:
    from app.services.consumption import get_total_stock_ul

    if current_stock_ul is None:
        current_stock_ul = get_total_stock_ul(antibody_id, session)

    # Add store stock (unopened vials) to total available supply for forecast
    from app.models import StoreStock
    store_lots = session.exec(
        select(StoreStock)
        .where(StoreStock.antibody_id == antibody_id)
        .where(StoreStock.quantity > 0)
    ).all()
    store_stock_ul = sum(s.quantity * s.volume_per_vial_ul for s in store_lots)
    total_supply_ul = current_stock_ul + store_stock_ul

    daily = _get_daily_consumption(antibody_id, session, history_days)

    if len(daily) == 0:
        return ForecastResult(
            antibody_id=antibody_id,
            current_stock_ul=current_stock_ul,
            store_stock_ul=store_stock_ul,
            depletion_date=None,
            days_remaining=None,
            avg_daily_ul=0.0,
            forecast_daily_ul=0.0,
            history_days=0,
            method="insufficient_data",
        )

    avg_daily = float(daily.mean())

    # len(daily) is the REINDEXED calendar length (~history_days), not an
    # observation count — _get_daily_consumption pads absent days with 0.0.
    # Gating on it made the ETS branch unconditional and the moving-average
    # fallback unreachable. Count days with recorded consumption instead.
    observed_days = int((daily > 0).sum())

    use_ets = FORECAST_METHOD == "ets" or (
        FORECAST_METHOD == "auto" and observed_days >= MIN_OBSERVED_DAYS_FOR_ETS
    )

    if use_ets:
        return _fit_ets(
            antibody_id=antibody_id,
            daily=daily,
            current_stock_ul=current_stock_ul,
            total_supply_ul=total_supply_ul,
            store_stock_ul=store_stock_ul,
            horizon=forecast_horizon_days,
            avg_daily=avg_daily,
        )
    else:
        return _moving_average_forecast(
            antibody_id=antibody_id,
            daily=daily,
            current_stock_ul=current_stock_ul,
            total_supply_ul=total_supply_ul,
            store_stock_ul=store_stock_ul,
            horizon=forecast_horizon_days,
            avg_daily=avg_daily,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_daily_consumption(
    antibody_id: int, session: Session, history_days: int
) -> pd.Series:
    cutoff = date.today() - timedelta(days=history_days)

    rows = session.exec(
        select(ConsumptionLog)
        .where(ConsumptionLog.antibody_id == antibody_id)
        .where(ConsumptionLog.timestamp >= cutoff)
    ).all()

    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame([
        {"date": row.timestamp.date(), "vol": row.volume_consumed_ul}
        for row in rows
    ])
    daily = df.groupby("date")["vol"].sum()

    full_index = pd.date_range(start=cutoff, end=date.today(), freq="D").date
    daily = daily.reindex(full_index, fill_value=0.0)
    return daily


def _fit_ets(
    antibody_id: int,
    daily: pd.Series,
    current_stock_ul: float,
    total_supply_ul: float,
    store_stock_ul: float,
    horizon: int,
    avg_daily: float,
) -> ForecastResult:
    y = daily.values.astype(float)

    try:
        alpha, beta, final_level, final_trend, resid_std = _optimise_holtwinters(y)

        # Generate forecast: ŷ_{t+h} = level + h * trend, clipped to >= 0
        forecast_values = np.array([
            max(0.0, final_level + (h + 1) * final_trend)
            for h in range(horizon)
        ])

        margin = 1.96 * resid_std
        forecast_daily = float(np.mean(forecast_values))

    except Exception:
        return _moving_average_forecast(
            antibody_id=antibody_id,
            daily=daily,
            current_stock_ul=current_stock_ul,
            total_supply_ul=total_supply_ul,
            store_stock_ul=store_stock_ul,
            horizon=horizon,
            avg_daily=avg_daily,
        )

    depletion_date, days_remaining = _compute_depletion(total_supply_ul, forecast_values)
    forecast_dates = [date.today() + timedelta(days=i + 1) for i in range(horizon)]

    return ForecastResult(
        antibody_id=antibody_id,
        current_stock_ul=current_stock_ul,
        store_stock_ul=store_stock_ul,
        depletion_date=depletion_date,
        days_remaining=days_remaining,
        avg_daily_ul=round(avg_daily, 3),
        forecast_daily_ul=round(forecast_daily, 3),
        history_days=len(daily),
        method="ets",
        forecast_series=[
            {"date": str(d), "predicted_ul": round(float(v), 2)}
            for d, v in zip(forecast_dates, forecast_values)
        ],
        confidence_low=[
            {"date": str(d), "predicted_ul": round(max(0.0, float(v) - margin), 2)}
            for d, v in zip(forecast_dates, forecast_values)
        ],
        confidence_high=[
            {"date": str(d), "predicted_ul": round(float(v) + margin, 2)}
            for d, v in zip(forecast_dates, forecast_values)
        ],
    )


def _moving_average_forecast(
    antibody_id: int,
    daily: pd.Series,
    current_stock_ul: float,
    total_supply_ul: float,
    store_stock_ul: float,
    horizon: int,
    avg_daily: float,
) -> ForecastResult:
    forecast_values = np.clip(np.full(horizon, avg_daily), 0, None)
    depletion_date, days_remaining = _compute_depletion(total_supply_ul, forecast_values)
    forecast_dates = [date.today() + timedelta(days=i + 1) for i in range(horizon)]

    return ForecastResult(
        antibody_id=antibody_id,
        current_stock_ul=current_stock_ul,
        store_stock_ul=store_stock_ul,
        depletion_date=depletion_date,
        days_remaining=days_remaining,
        avg_daily_ul=round(avg_daily, 3),
        forecast_daily_ul=round(avg_daily, 3),
        history_days=len(daily),
        method="moving_average",
        forecast_series=[
            {"date": str(d), "predicted_ul": round(float(v), 2)}
            for d, v in zip(forecast_dates, forecast_values)
        ],
        confidence_low=[],
        confidence_high=[],
    )


def _compute_depletion(
    current_stock_ul: float, forecast_values: np.ndarray
) -> Tuple[Optional[date], Optional[float]]:
    if current_stock_ul <= 0:
        return date.today(), 0.0

    cumulative = 0.0
    for i, daily_val in enumerate(forecast_values):
        cumulative += daily_val
        if cumulative >= current_stock_ul:
            days = i + 1
            return date.today() + timedelta(days=days), float(days)

    remaining = current_stock_ul - float(np.sum(forecast_values))
    nonzero = forecast_values[forecast_values > 0]
    last_daily = float(nonzero.mean()) if len(nonzero) > 0 else 0.0

    if last_daily <= 0:
        return None, None

    extra_days = remaining / last_daily
    total_days = len(forecast_values) + extra_days
    return date.today() + timedelta(days=total_days), round(total_days, 1)


def run_all_forecasts(session: Session) -> List[ForecastResult]:
    from app.models import Antibody
    antibodies = session.exec(select(Antibody).where(Antibody.active == True)).all()
    return [forecast_antibody(ab.id, session) for ab in antibodies]
