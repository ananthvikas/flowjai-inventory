"""routers/antibodies.py — CRUD for antibodies and their alternatives."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin
from app.database import get_session
from app.models import Antibody, AntibodyAlternative, Fluorochrome, User
from app.services.vial_volume import validate_master_volume

router = APIRouter(prefix="/api/antibodies", tags=["antibodies"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AntibodyCreate(BaseModel):
    name: str
    clone: Optional[str] = None
    vendor: Optional[str] = None
    catalog_no: Optional[str] = None
    vial_volume_ul: Optional[float] = None
    fluorochrome_id: Optional[int] = None


class AntibodyUpdate(BaseModel):
    name: Optional[str] = None
    clone: Optional[str] = None
    vendor: Optional[str] = None
    catalog_no: Optional[str] = None
    # Send null explicitly to clear the standard volume.
    vial_volume_ul: Optional[float] = None
    fluorochrome_id: Optional[int] = None
    active: Optional[bool] = None


class FluorochromeRead(BaseModel):
    id: int
    name: str
    laser: Optional[str]


class AntibodyRead(BaseModel):
    id: int
    name: str
    clone: Optional[str]
    vendor: Optional[str]
    catalog_no: Optional[str]
    vial_volume_ul: Optional[float] = None
    fluorochrome_id: Optional[int]
    fluorochrome: Optional[FluorochromeRead]
    active: bool


class AlternativeCreate(BaseModel):
    alt_antibody_id: int
    note: Optional[str] = None


class AlternativeRead(BaseModel):
    id: int
    antibody_id: int
    alt_antibody_id: int
    alt_antibody_name: str
    alt_fluorochrome: Optional[str]
    note: Optional[str]


# ---------------------------------------------------------------------------
# Antibody CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[AntibodyRead])
def list_antibodies(
    active_only: bool = True,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(Antibody)
    if active_only:
        q = q.where(Antibody.active == True)    # noqa: E712
    antibodies = session.exec(q.order_by(Antibody.name)).all()

    result = []
    for ab in antibodies:
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None
        result.append(AntibodyRead(
            id=ab.id,
            name=ab.name,
            clone=ab.clone,
            vendor=ab.vendor,
            catalog_no=ab.catalog_no,
            vial_volume_ul=ab.vial_volume_ul,
            fluorochrome_id=ab.fluorochrome_id,
            fluorochrome=FluorochromeRead(id=fc.id, name=fc.name, laser=fc.laser) if fc else None,
            active=ab.active,
        ))
    return result


@router.get("/{antibody_id}", response_model=AntibodyRead)
def get_antibody(
    antibody_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    ab = session.get(Antibody, antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")
    fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None
    return AntibodyRead(
        id=ab.id,
        name=ab.name,
        clone=ab.clone,
        vendor=ab.vendor,
        catalog_no=ab.catalog_no,
            vial_volume_ul=ab.vial_volume_ul,
        fluorochrome_id=ab.fluorochrome_id,
        fluorochrome=FluorochromeRead(id=fc.id, name=fc.name, laser=fc.laser) if fc else None,
        active=ab.active,
    )


@router.post("/", response_model=AntibodyRead, dependencies=[Depends(require_admin)])
def create_antibody(payload: AntibodyCreate, session: Session = Depends(get_session)):
    try:
        validate_master_volume(payload.vial_volume_ul)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ab = Antibody(**payload.model_dump())
    session.add(ab)
    session.commit()
    session.refresh(ab)
    fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None
    return AntibodyRead(
        id=ab.id, name=ab.name, clone=ab.clone, vendor=ab.vendor,
        catalog_no=ab.catalog_no, vial_volume_ul=ab.vial_volume_ul,
        fluorochrome_id=ab.fluorochrome_id,
        fluorochrome=FluorochromeRead(id=fc.id, name=fc.name, laser=fc.laser) if fc else None,
        active=ab.active,
    )


@router.patch("/{antibody_id}", response_model=AntibodyRead, dependencies=[Depends(require_admin)])
def update_antibody(
    antibody_id: int, payload: AntibodyUpdate, session: Session = Depends(get_session)
):
    ab = session.get(Antibody, antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    data = payload.model_dump(exclude_none=True)
    data.pop("vial_volume_ul", None)
    for k, v in data.items():
        setattr(ab, k, v)
    if "vial_volume_ul" in payload.model_fields_set:      # explicit null clears it
        try:
            ab.vial_volume_ul = validate_master_volume(payload.vial_volume_ul)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    session.add(ab)
    session.commit()
    session.refresh(ab)
    fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None
    return AntibodyRead(
        id=ab.id, name=ab.name, clone=ab.clone, vendor=ab.vendor,
        catalog_no=ab.catalog_no, vial_volume_ul=ab.vial_volume_ul,
        fluorochrome_id=ab.fluorochrome_id,
        fluorochrome=FluorochromeRead(id=fc.id, name=fc.name, laser=fc.laser) if fc else None,
        active=ab.active,
    )


# ---------------------------------------------------------------------------
# Alternatives sub-resource
# ---------------------------------------------------------------------------

@router.get("/{antibody_id}/alternatives", response_model=List[AlternativeRead])
def list_alternatives(
    antibody_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    alts = session.exec(
        select(AntibodyAlternative)
        .where(AntibodyAlternative.antibody_id == antibody_id)
    ).all()

    result = []
    for alt in alts:
        alt_ab = session.get(Antibody, alt.alt_antibody_id)
        fc = session.get(Fluorochrome, alt_ab.fluorochrome_id) if (alt_ab and alt_ab.fluorochrome_id) else None
        result.append(AlternativeRead(
            id=alt.id,
            antibody_id=alt.antibody_id,
            alt_antibody_id=alt.alt_antibody_id,
            alt_antibody_name=alt_ab.name if alt_ab else "unknown",
            alt_fluorochrome=fc.name if fc else None,
            note=alt.note,
        ))
    return result


@router.post(
    "/{antibody_id}/alternatives",
    response_model=AlternativeRead,
    dependencies=[Depends(require_admin)],
)
def add_alternative(
    antibody_id: int, payload: AlternativeCreate, session: Session = Depends(get_session)
):
    if antibody_id == payload.alt_antibody_id:
        raise HTTPException(status_code=400, detail="An antibody cannot be its own alternative")

    source = session.get(Antibody, antibody_id)
    alt_ab = session.get(Antibody, payload.alt_antibody_id)
    if not source or not alt_ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    existing = session.exec(
        select(AntibodyAlternative)
        .where(AntibodyAlternative.antibody_id == antibody_id)
        .where(AntibodyAlternative.alt_antibody_id == payload.alt_antibody_id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Alternative already exists")

    alt = AntibodyAlternative(
        antibody_id=antibody_id,
        alt_antibody_id=payload.alt_antibody_id,
        note=payload.note,
    )
    session.add(alt)
    session.commit()
    session.refresh(alt)

    fc = session.get(Fluorochrome, alt_ab.fluorochrome_id) if alt_ab.fluorochrome_id else None
    return AlternativeRead(
        id=alt.id,
        antibody_id=alt.antibody_id,
        alt_antibody_id=alt.alt_antibody_id,
        alt_antibody_name=alt_ab.name,
        alt_fluorochrome=fc.name if fc else None,
        note=alt.note,
    )


@router.delete(
    "/{antibody_id}/alternatives/{alt_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
def remove_alternative(
    antibody_id: int, alt_id: int, session: Session = Depends(get_session)
):
    alt = session.get(AntibodyAlternative, alt_id)
    if not alt or alt.antibody_id != antibody_id:
        raise HTTPException(status_code=404, detail="Alternative not found")
    session.delete(alt)
    session.commit()


@router.get("/{antibody_id}/delete-preview", dependencies=[Depends(require_admin)])
def antibody_delete_preview(antibody_id: int, session: Session = Depends(get_session)):
    """
    Returns a summary of all records that would be cascade-deleted with this antibody.
    Used by the frontend to show a confirmation dialog before force-delete.
    """
    from app.models import StockLot, PanelComponent, ConsumptionLog, AntibodyAlternative, VerificationLog, Order, AlertRule, Alert
    from sqlmodel import select

    ab = session.get(Antibody, antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    lots       = session.exec(select(StockLot).where(StockLot.antibody_id == antibody_id)).all()
    comps      = session.exec(select(PanelComponent).where(PanelComponent.antibody_id == antibody_id)).all()
    cons_logs  = session.exec(select(ConsumptionLog).where(ConsumptionLog.antibody_id == antibody_id)).all()
    ver_logs   = session.exec(select(VerificationLog).where(VerificationLog.antibody_id == antibody_id)).all()
    orders     = session.exec(select(Order).where(Order.antibody_id == antibody_id)).all()
    alert_rules= session.exec(select(AlertRule).where(AlertRule.antibody_id == antibody_id)).all()
    alerts     = session.exec(select(Alert).where(Alert.antibody_id == antibody_id)).all()
    alts       = session.exec(
        select(AntibodyAlternative).where(
            (AntibodyAlternative.antibody_id == antibody_id) |
            (AntibodyAlternative.alt_antibody_id == antibody_id)
        )
    ).all()

    return {
        "antibody_name": ab.name,
        "stock_lots": len(lots),
        "panel_assignments": len(comps),
        "consumption_logs": len(cons_logs),
        "verification_logs": len(ver_logs),
        "orders": len(orders),
        "alert_rules": len(alert_rules),
        "alerts": len(alerts),
        "alternative_mappings": len(alts),
        "safe": len(lots) == 0 and len(comps) == 0 and len(cons_logs) == 0,
    }


@router.delete(
    "/{antibody_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
def delete_antibody(
    antibody_id: int,
    force: bool = False,
    session: Session = Depends(get_session),
):
    """
    Delete an antibody.
    - Normal delete: blocked if the antibody has any dependent records.
    - Force delete (?force=true): admin cascade-deletes all dependent records.
      Intended for removing placeholder/seed data from a fresh deployment.
    """
    from app.models import StockLot, PanelComponent, ConsumptionLog, AntibodyAlternative, VerificationLog
    from sqlmodel import select

    ab = session.get(Antibody, antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    lots      = session.exec(select(StockLot).where(StockLot.antibody_id == antibody_id)).all()
    comps     = session.exec(select(PanelComponent).where(PanelComponent.antibody_id == antibody_id)).all()
    cons_logs = session.exec(select(ConsumptionLog).where(ConsumptionLog.antibody_id == antibody_id)).all()
    ver_logs  = session.exec(select(VerificationLog).where(VerificationLog.antibody_id == antibody_id)).all()
    alts      = session.exec(
        select(AntibodyAlternative).where(
            (AntibodyAlternative.antibody_id == antibody_id) |
            (AntibodyAlternative.alt_antibody_id == antibody_id)
        )
    ).all()

    has_dependents = lots or comps or cons_logs

    if has_dependents and not force:
        parts = []
        if lots:      parts.append(f"{len(lots)} stock lot(s)")
        if comps:     parts.append(f"{len(comps)} panel assignment(s)")
        if cons_logs: parts.append(f"{len(cons_logs)} consumption record(s)")
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: antibody has {', '.join(parts)}. Use force delete to remove everything.",
        )

    # Collect remaining dependent records not yet queried
    from app.models import Order, AlertRule, Alert
    orders     = session.exec(select(Order).where(Order.antibody_id == antibody_id)).all()
    alert_rules= session.exec(select(AlertRule).where(AlertRule.antibody_id == antibody_id)).all()
    alerts     = session.exec(select(Alert).where(Alert.antibody_id == antibody_id)).all()

    # Also catch any consumption/verification logs tied to this antibody's lots
    # (belt-and-suspenders: covers any rows where antibody_id linkage is inconsistent)
    for lot in lots:
        extra_cons = session.exec(select(ConsumptionLog).where(ConsumptionLog.stock_lot_id == lot.id)).all()
        for r in extra_cons:
            if r not in cons_logs:
                session.delete(r)
        extra_ver = session.exec(select(VerificationLog).where(VerificationLog.stock_lot_id == lot.id)).all()
        for r in extra_ver:
            if r not in ver_logs:
                session.delete(r)

    # Cascade in dependency order (children before parents)
    for r in cons_logs:   session.delete(r)
    for r in ver_logs:    session.delete(r)
    for r in lots:        session.delete(r)
    for r in comps:       session.delete(r)
    for r in alts:        session.delete(r)
    for r in orders:      session.delete(r)
    for r in alerts:      session.delete(r)
    for r in alert_rules: session.delete(r)
    try:
        session.delete(ab)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
