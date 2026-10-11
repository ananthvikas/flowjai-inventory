"""routers/alerts.py — Alert retrieval, acknowledgement, and manual trigger."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_technologist_or_admin
from app.database import get_session
from app.models import Alert, Antibody, User
from app.services.alerts import run_alert_check

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertRead(BaseModel):
    id: int
    antibody_id: int
    antibody_name: str
    alert_type: str
    message: str
    days_remaining: Optional[float]
    triggered_at: datetime
    acknowledged_by: Optional[int]
    acknowledged_at: Optional[datetime]


def _enrich(alert: Alert, session: Session) -> AlertRead:
    ab = session.get(Antibody, alert.antibody_id)
    return AlertRead(
        id=alert.id,
        antibody_id=alert.antibody_id,
        antibody_name=ab.name if ab else "unknown",
        alert_type=alert.alert_type,
        message=alert.message,
        days_remaining=alert.days_remaining,
        triggered_at=alert.triggered_at,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
    )


@router.get("/", response_model=List[AlertRead])
def list_alerts(
    unacknowledged_only: bool = True,
    alert_type: Optional[str] = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(Alert).order_by(Alert.triggered_at.desc())
    if unacknowledged_only:
        q = q.where(Alert.acknowledged_at == None)    # noqa: E711
    if alert_type:
        q = q.where(Alert.alert_type == alert_type)
    alerts = session.exec(q).all()
    return [_enrich(a, session) for a in alerts]


@router.post("/run", response_model=List[AlertRead])
def trigger_alert_check(
    session: Session = Depends(get_session),
    _: User = Depends(require_technologist_or_admin),
):
    """Manually trigger the alert pipeline. Also runs automatically after test log creation."""
    new_alerts = run_alert_check(session)
    session.commit()
    return [_enrich(a, session) for a in new_alerts]


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.acknowledged_at is not None:
        raise HTTPException(status_code=409, detail="Alert already acknowledged")

    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.now()
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return _enrich(alert, session)
