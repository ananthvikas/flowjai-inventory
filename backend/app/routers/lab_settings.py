"""
routers/lab_settings.py

Admin-configurable lab identity and system-wide alert defaults.

Lab settings are stored as key/value pairs in LabSetting.
Global alert defaults are stored in a single-row GlobalAlertDefault table.
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin
from app.database import get_session
from app.models import GlobalAlertDefault, LabSetting, User

router = APIRouter(prefix="/api/lab-settings", tags=["lab-settings"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LabSettingsRead(BaseModel):
    lab_name: Optional[str]
    lab_subtitle: Optional[str]


class LabSettingsUpdate(BaseModel):
    lab_name: Optional[str] = None
    lab_subtitle: Optional[str] = None


class GlobalAlertDefaultsRead(BaseModel):
    lead_time_days: int
    alert_threshold_days: int
    safety_stock_ul: float


class GlobalAlertDefaultsUpdate(BaseModel):
    lead_time_days: int
    alert_threshold_days: int
    safety_stock_ul: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_setting(key: str, session: Session) -> Optional[str]:
    row = session.get(LabSetting, key)
    return row.value if row else None


def _set_setting(key: str, value: Optional[str], session: Session):
    row = session.get(LabSetting, key)
    if row:
        row.value = value
        row.updated_at = datetime.now()
    else:
        row = LabSetting(key=key, value=value)
    session.add(row)


def _get_global_defaults(session: Session) -> GlobalAlertDefault:
    defaults = session.exec(select(GlobalAlertDefault)).first()
    if not defaults:
        defaults = GlobalAlertDefault()
        session.add(defaults)
        session.commit()
        session.refresh(defaults)
    return defaults


# ---------------------------------------------------------------------------
# Lab identity endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=LabSettingsRead)
def get_lab_settings(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    return LabSettingsRead(
        lab_name=_get_setting("lab_name", session),
        lab_subtitle=_get_setting("lab_subtitle", session),
    )


@router.patch("/", response_model=LabSettingsRead, dependencies=[Depends(require_admin)])
def update_lab_settings(
    payload: LabSettingsUpdate,
    session: Session = Depends(get_session),
):
    if payload.lab_name is not None:
        _set_setting("lab_name", payload.lab_name or None, session)
    if payload.lab_subtitle is not None:
        _set_setting("lab_subtitle", payload.lab_subtitle or None, session)
    session.commit()
    return LabSettingsRead(
        lab_name=_get_setting("lab_name", session),
        lab_subtitle=_get_setting("lab_subtitle", session),
    )


# ---------------------------------------------------------------------------
# Global alert defaults
# ---------------------------------------------------------------------------

@router.get("/alert-defaults", response_model=GlobalAlertDefaultsRead)
def get_alert_defaults(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    d = _get_global_defaults(session)
    return GlobalAlertDefaultsRead(
        lead_time_days=d.lead_time_days,
        alert_threshold_days=d.alert_threshold_days,
        safety_stock_ul=d.safety_stock_ul,
    )


@router.put(
    "/alert-defaults",
    response_model=GlobalAlertDefaultsRead,
    dependencies=[Depends(require_admin)],
)
def update_alert_defaults(
    payload: GlobalAlertDefaultsUpdate,
    session: Session = Depends(get_session),
):
    d = _get_global_defaults(session)
    d.lead_time_days = payload.lead_time_days
    d.alert_threshold_days = payload.alert_threshold_days
    d.safety_stock_ul = payload.safety_stock_ul
    d.updated_at = datetime.now()
    session.add(d)
    session.commit()
    session.refresh(d)
    return GlobalAlertDefaultsRead(
        lead_time_days=d.lead_time_days,
        alert_threshold_days=d.alert_threshold_days,
        safety_stock_ul=d.safety_stock_ul,
    )
