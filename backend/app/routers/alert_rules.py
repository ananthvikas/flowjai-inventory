"""routers/alert_rules.py — Per-antibody alert threshold configuration (admin only)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import require_admin
from app.database import get_session
from app.models import Antibody, AlertRule

router = APIRouter(prefix="/api/alert-rules", tags=["alert-rules"])


class AlertRuleUpsert(BaseModel):
    lead_time_days: int = 35
    safety_stock_ul: float = 0.0
    alert_threshold_days: int = 42


class AlertRuleRead(BaseModel):
    id: int
    antibody_id: int
    antibody_name: str
    lead_time_days: int
    safety_stock_ul: float
    alert_threshold_days: int


def _enrich(rule: AlertRule, session: Session) -> AlertRuleRead:
    ab = session.get(Antibody, rule.antibody_id)
    return AlertRuleRead(
        id=rule.id,
        antibody_id=rule.antibody_id,
        antibody_name=ab.name if ab else "unknown",
        lead_time_days=rule.lead_time_days,
        safety_stock_ul=rule.safety_stock_ul,
        alert_threshold_days=rule.alert_threshold_days,
    )


@router.get("/", response_model=List[AlertRuleRead], dependencies=[Depends(require_admin)])
def list_rules(session: Session = Depends(get_session)):
    rules = session.exec(select(AlertRule)).all()
    return [_enrich(r, session) for r in rules]


@router.put("/{antibody_id}", response_model=AlertRuleRead, dependencies=[Depends(require_admin)])
def upsert_rule(
    antibody_id: int,
    payload: AlertRuleUpsert,
    session: Session = Depends(get_session),
):
    ab = session.get(Antibody, antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    rule = session.exec(
        select(AlertRule).where(AlertRule.antibody_id == antibody_id)
    ).first()

    if rule:
        rule.lead_time_days = payload.lead_time_days
        rule.safety_stock_ul = payload.safety_stock_ul
        rule.alert_threshold_days = payload.alert_threshold_days
    else:
        rule = AlertRule(
            antibody_id=antibody_id,
            **payload.model_dump(),
        )

    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _enrich(rule, session)


@router.delete("/{antibody_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_rule(antibody_id: int, session: Session = Depends(get_session)):
    rule = session.exec(
        select(AlertRule).where(AlertRule.antibody_id == antibody_id)
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="No custom rule for this antibody")
    session.delete(rule)
    session.commit()
