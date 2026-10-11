"""routers/forecast.py — Depletion forecasts per antibody or all antibodies."""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.services.forecast import ForecastResult, forecast_antibody, run_all_forecasts

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


class ForecastRead(BaseModel):
    antibody_id: int
    current_stock_ul: float
    depletion_date: Optional[str]
    days_remaining: Optional[float]
    avg_daily_ul: float
    forecast_daily_ul: float
    history_days: int
    method: str
    forecast_series: List[Dict]
    confidence_low: List[Dict]
    confidence_high: List[Dict]


def _to_read(r: ForecastResult) -> ForecastRead:
    return ForecastRead(
        antibody_id=r.antibody_id,
        current_stock_ul=r.current_stock_ul,
        depletion_date=str(r.depletion_date) if r.depletion_date else None,
        days_remaining=r.days_remaining,
        avg_daily_ul=r.avg_daily_ul,
        forecast_daily_ul=r.forecast_daily_ul,
        history_days=r.history_days,
        method=r.method,
        forecast_series=r.forecast_series,
        confidence_low=r.confidence_low,
        confidence_high=r.confidence_high,
    )


@router.get("/", response_model=List[ForecastRead])
def get_all_forecasts(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Run forecasts for all active antibodies. Used by dashboard."""
    results = run_all_forecasts(session)
    return [_to_read(r) for r in results]


@router.get("/{antibody_id}", response_model=ForecastRead)
def get_antibody_forecast(
    antibody_id: int,
    history_days: int = 90,
    horizon_days: int = 60,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    result = forecast_antibody(
        antibody_id=antibody_id,
        session=session,
        history_days=history_days,
        forecast_horizon_days=horizon_days,
    )
    return _to_read(result)
