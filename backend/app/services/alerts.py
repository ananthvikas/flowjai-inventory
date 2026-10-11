"""
services/alerts.py

Alert generation pipeline. Intended to run:
  - On demand (POST /api/alerts/run)
  - Automatically after each test_log creation (lightweight check)
  - On a schedule (can be wired to APScheduler or a cron-triggered endpoint)

Two alert types generated here:
  shortage              — days_remaining < alert_threshold_days
  substitute_suggestion — shortage AND at least one alternative exists
  expiry_warning        — a lot expires within 30 days with >20µl remaining

De-duplication: an alert is not re-raised if an unacknowledged alert of the same
type for the same antibody already exists from within the last 24 hours.
"""


from datetime import datetime, timedelta
from typing import List, Optional

from sqlmodel import Session, select

from app.models import Alert, AlertRule, Antibody, AntibodyAlternative, StockLot
from app.services.forecast import ForecastResult, forecast_antibody


DEFAULT_LEAD_TIME_DAYS = 35
DEFAULT_SAFETY_BUFFER_DAYS = 7
DEFAULT_ALERT_THRESHOLD_DAYS = DEFAULT_LEAD_TIME_DAYS + DEFAULT_SAFETY_BUFFER_DAYS


def _get_global_defaults(session: Session):
    """Fetch system-wide defaults, falling back to hardcoded values."""
    from app.models import GlobalAlertDefault
    from sqlmodel import select
    defaults = session.exec(select(GlobalAlertDefault)).first()
    if defaults:
        return defaults.lead_time_days, defaults.alert_threshold_days, defaults.safety_stock_ul
    return DEFAULT_LEAD_TIME_DAYS, DEFAULT_ALERT_THRESHOLD_DAYS, 0.0


def run_alert_check(session: Session) -> List[Alert]:
    """
    Run the full alert pipeline. Returns all newly created Alert rows.
    Call session.commit() after this returns if you want them persisted.
    """
    antibodies = session.exec(select(Antibody).where(Antibody.active == True)).all()
    new_alerts: List[Alert] = []

    for antibody in antibodies:
        rule = _get_rule(antibody.id, session)
        forecast = forecast_antibody(antibody.id, session)

        # --- Shortage / substitute alerts ---
        if forecast.days_remaining is not None:
            if forecast.days_remaining < rule.alert_threshold_days:
                alert = _maybe_create_alert(
                    antibody_id=antibody.id,
                    alert_type="shortage",
                    message=(
                        f"{antibody.name} ({antibody.fluorochrome.name if antibody.fluorochrome else 'unknown fluor'}) "
                        f"projected to run out in {forecast.days_remaining:.0f} days "
                        f"({forecast.depletion_date}). Current stock: {forecast.current_stock_ul:.0f} µl."
                    ),
                    days_remaining=forecast.days_remaining,
                    session=session,
                )
                if alert:
                    session.add(alert)
                    new_alerts.append(alert)

                # Substitution suggestion if alternatives exist
                sub_alert = _check_substitutes(antibody, forecast, session)
                if sub_alert:
                    session.add(sub_alert)
                    new_alerts.append(sub_alert)

        # --- Expiry warnings ---
        expiry_alerts = _check_expiry(antibody, session)
        for ea in expiry_alerts:
            session.add(ea)
            new_alerts.append(ea)

    # --- Cocktail expiry warnings (checked once, not per-antibody) ---
    cocktail_alerts = _check_cocktail_expiry(session)
    for ca in cocktail_alerts:
        session.add(ca)
        new_alerts.append(ca)

    # --- Shipment verifications past their 48 h window ---
    from app.services.shipments import check_overdue
    new_alerts.extend(check_overdue(session))

    return new_alerts


def _get_rule(antibody_id: int, session: Session) -> AlertRule:
    """Returns existing AlertRule or a virtual default using global DB settings."""
    rule = session.exec(
        select(AlertRule).where(AlertRule.antibody_id == antibody_id)
    ).first()
    if rule is None:
        lead_time, threshold, safety = _get_global_defaults(session)
        rule = AlertRule(
            antibody_id=antibody_id,
            lead_time_days=lead_time,
            safety_stock_ul=safety,
            alert_threshold_days=threshold,
        )
    return rule


def _maybe_create_alert(
    antibody_id: int,
    alert_type: str,
    message: str,
    days_remaining: Optional[float],
    session: Session,
) -> Optional[Alert]:
    """Returns a new Alert only if no unacknowledged alert of this type exists within 24h."""
    cutoff = datetime.now() - timedelta(hours=24)
    existing = session.exec(
        select(Alert)
        .where(Alert.antibody_id == antibody_id)
        .where(Alert.alert_type == alert_type)
        .where(Alert.acknowledged_at == None)    # noqa: E711
        .where(Alert.triggered_at >= cutoff)
    ).first()

    if existing:
        return None  # de-duplicated

    return Alert(
        antibody_id=antibody_id,
        alert_type=alert_type,
        message=message,
        days_remaining=days_remaining,
        triggered_at=datetime.now(),
    )


def _check_substitutes(
    antibody: Antibody,
    forecast: ForecastResult,
    session: Session,
) -> Optional[Alert]:
    """Raises a substitute_suggestion alert if alternatives with stock exist."""
    alternatives: List[AntibodyAlternative] = session.exec(
        select(AntibodyAlternative)
        .where(AntibodyAlternative.antibody_id == antibody.id)
    ).all()

    if not alternatives:
        return None

    alt_names = []
    for alt in alternatives:
        alt_ab = session.get(Antibody, alt.alt_antibody_id)
        if alt_ab and alt_ab.active:
            from app.services.consumption import get_total_stock_ul
            alt_stock = get_total_stock_ul(alt_ab.id, session)
            fluor = alt_ab.fluorochrome.name if alt_ab.fluorochrome else "unknown"
            stock_note = f"{alt_stock:.0f} µl" if alt_stock > 0 else "no stock"
            note = f" ({alt.note})" if alt.note else ""
            alt_names.append(f"{alt_ab.name}-{fluor}{note} [{stock_note}]")

    if not alt_names:
        return None

    message = (
        f"Substitute options for {antibody.name} (running out in "
        f"{forecast.days_remaining:.0f} days): {', '.join(alt_names)}."
    )

    return _maybe_create_alert(
        antibody_id=antibody.id,
        alert_type="substitute_suggestion",
        message=message,
        days_remaining=forecast.days_remaining,
        session=session,
    )


def _check_expiry(antibody: Antibody, session: Session) -> List[Alert]:
    """Raises expiry_warning for lots expiring within 30 days that still have stock."""
    from datetime import date

    alerts: List[Alert] = []
    warn_cutoff = date.today() + timedelta(days=30)

    lots: List[StockLot] = session.exec(
        select(StockLot)
        .where(StockLot.antibody_id == antibody.id)
        .where(StockLot.active == True)
        .where(StockLot.expiry_date != None)     # noqa: E711
        .where(StockLot.expiry_date <= warn_cutoff)
        .where(StockLot.current_volume_ul > 20)  # more than 20 µl — worth flagging
    ).all()

    for lot in lots:
        days_to_expiry = (lot.expiry_date - date.today()).days
        message = (
            f"Lot {lot.lot_no} of {antibody.name} expires in {days_to_expiry} days "
            f"({lot.expiry_date}) with {lot.current_volume_ul:.0f} µl remaining."
        )
        alert = _maybe_create_alert(
            antibody_id=antibody.id,
            alert_type="expiry_warning",
            message=message,
            days_remaining=float(days_to_expiry),
            session=session,
        )
        if alert:
            alerts.append(alert)

    return alerts

def _check_cocktail_expiry(session: Session) -> List[Alert]:
    """
    Raises expiry_warning for active cocktails expiring within 3 days.
    Uses antibody_id=0 as a sentinel since alerts are antibody-keyed.
    Stores cocktail info in the message. Raises against the first antibody
    in the panel as a proxy so the alert appears in the feed meaningfully.
    """
    from datetime import date
    from app.models import Cocktail, Panel, PanelComponent

    alerts: List[Alert] = []
    warn_cutoff = date.today() + timedelta(days=3)

    cocktails = session.exec(
        select(Cocktail)
        .where(Cocktail.active == True)            # noqa: E712
        .where(Cocktail.expiry_date != None)       # noqa: E711
        .where(Cocktail.expiry_date <= warn_cutoff)
        .where(Cocktail.remaining_tests > 0)
    ).all()

    for c in cocktails:
        panel = session.get(Panel, c.panel_id)
        panel_name = panel.name if panel else f"panel {c.panel_id}"
        days_to_expiry = (c.expiry_date - date.today()).days

        # Find a proxy antibody_id from the panel (for the alert key)
        comp = session.exec(
            select(PanelComponent).where(PanelComponent.panel_id == c.panel_id)
        ).first()
        if not comp:
            continue
        antibody_id = comp.antibody_id

        message = (
            f"Cocktail '{panel_name}'"
            f"{f' ({c.lot_notes})' if c.lot_notes else ''} "
            f"expires in {days_to_expiry} day{'s' if days_to_expiry != 1 else ''} "
            f"({c.expiry_date}) with {c.remaining_tests} tests remaining."
        )
        alert = _maybe_create_alert(
            antibody_id=antibody_id,
            alert_type="cocktail_expiry",
            message=message,
            days_remaining=float(days_to_expiry),
            session=session,
        )
        if alert:
            alerts.append(alert)

    return alerts
