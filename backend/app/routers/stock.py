"""routers/stock.py — Stock lot management (receive, verify, view)."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin, require_technologist_or_admin
from app.database import get_session
from app.models import Antibody, StockLot, StoreStock, User
from app.services.consumption import get_total_stock_ul, verify_stock_volume
from app.services.vial_volume import (
    CORRECTION_TAG, OVERRIDE_TAG, TOLERANCE_UL, append_note, is_overridden, resolve_vial_volume,
)
from app.services.shipments import ensure_shipment_verification, normalise_shipment_id

router = APIRouter(prefix="/api/stock", tags=["stock"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StockLotCreate(BaseModel):
    antibody_id: int
    lot_no: str
    # Omit to use the antibody's standard vial volume. A different value is
    # accepted only with volume_override_reason.
    initial_volume_ul: Optional[float] = None
    volume_override_reason: Optional[str] = None
    date_received: date
    date_opened: Optional[date] = None
    expiry_date: Optional[date] = None
    shipment_id: Optional[str] = None


class StockLotRead(BaseModel):
    id: int
    antibody_id: int
    antibody_name: str
    vendor: Optional[str]
    fluorochrome: Optional[str]
    lot_no: str
    initial_volume_ul: float
    current_volume_ul: float
    date_received: date
    date_opened: Optional[date]
    expiry_date: Optional[date]
    last_verified_date: Optional[date]
    last_verified_volume_ul: Optional[float]
    shipment_id: Optional[str] = None
    notes: Optional[str] = None
    active: bool
    percent_remaining: float
    store_vial_count: int


class VerifyPayload(BaseModel):
    verified_volume_ul: float
    measurement_method: str = "pipette"           # "pipette" | "gravimetric"
    pipette_increment_ul: Optional[float] = None  # resolution floor (e.g. 5.0)
    verification_cycle: Optional[str] = None      # label grouping verifications (e.g. prep batch)


class StockSummary(BaseModel):
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    vendor: Optional[str]
    total_stock_ul: float
    active_lot_count: int
    oldest_expiry: Optional[date]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich_lot(lot: StockLot, session: Session, store_vial_count: int = 0) -> StockLotRead:
    ab = session.get(Antibody, lot.antibody_id)
    pct = (lot.current_volume_ul / lot.initial_volume_ul * 100) if lot.initial_volume_ul else 0
    fluor = None
    if ab and ab.fluorochrome_id:
        from app.models import Fluorochrome
        fc = session.get(Fluorochrome, ab.fluorochrome_id)
        fluor = fc.name if fc else None
    return StockLotRead(
        id=lot.id,
        antibody_id=lot.antibody_id,
        antibody_name=ab.name if ab else "unknown",
        vendor=ab.vendor if ab else None,
        fluorochrome=fluor,
        lot_no=lot.lot_no,
        initial_volume_ul=lot.initial_volume_ul,
        current_volume_ul=lot.current_volume_ul,
        date_received=lot.date_received,
        date_opened=lot.date_opened,
        expiry_date=lot.expiry_date,
        last_verified_date=lot.last_verified_date,
        last_verified_volume_ul=lot.last_verified_volume_ul,
        shipment_id=lot.shipment_id,
        notes=lot.notes,
        active=lot.active,
        percent_remaining=round(pct, 1),
        store_vial_count=store_vial_count,
    )


def _new_lot(payload: "StockLotCreate", ab: Antibody) -> StockLot:
    """Build a lot, applying the antibody master's standard vial volume.
    Raises ValueError on a non-standard volume without a reason."""
    volume, note = resolve_vial_volume(ab, payload.initial_volume_ul, payload.volume_override_reason)
    data = payload.model_dump(exclude={"initial_volume_ul", "volume_override_reason"})
    data["shipment_id"] = normalise_shipment_id(data.get("shipment_id"))
    return StockLot(**data, initial_volume_ul=volume, current_volume_ul=volume, notes=note)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[StockLotRead])
def list_lots(
    antibody_id: Optional[int] = None,
    active_only: bool = True,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(StockLot)
    if antibody_id:
        q = q.where(StockLot.antibody_id == antibody_id)
    if active_only:
        q = q.where(StockLot.active == True)    # noqa: E712
    lots = session.exec(q.order_by(StockLot.date_received)).all()

    # Pre-fetch store stock vial counts per antibody (single query, no N+1)
    from app.models import StoreStock
    from sqlmodel import func
    store_counts: dict[int, int] = {}
    if lots:
        ab_ids = list({lot.antibody_id for lot in lots})
        store_rows = session.exec(
            select(StoreStock.antibody_id, func.sum(StoreStock.quantity))
            .where(StoreStock.antibody_id.in_(ab_ids))
            .where(StoreStock.quantity > 0)
            .group_by(StoreStock.antibody_id)
        ).all()
        store_counts = {ab_id: int(total) for ab_id, total in store_rows}

    return [_enrich_lot(lot, session, store_counts.get(lot.antibody_id, 0)) for lot in lots]


@router.get("/summary", response_model=List[StockSummary])
def stock_summary(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Per-antibody summary: total active stock, lot count, earliest expiry."""
    antibodies = session.exec(select(Antibody).where(Antibody.active == True)).all()   # noqa: E712
    result = []
    for ab in antibodies:
        lots = session.exec(
            select(StockLot)
            .where(StockLot.antibody_id == ab.id)
            .where(StockLot.active == True)       # noqa: E712
        ).all()

        total = sum(lot.current_volume_ul for lot in lots)
        expiry_dates = [lot.expiry_date for lot in lots if lot.expiry_date]
        oldest_expiry = min(expiry_dates) if expiry_dates else None
        fc = ab.fluorochrome.name if ab.fluorochrome else None

        result.append(StockSummary(
            antibody_id=ab.id,
            antibody_name=ab.name,
            fluorochrome=fc,
            vendor=ab.vendor,
            total_stock_ul=round(total, 2),
            active_lot_count=len(lots),
            oldest_expiry=oldest_expiry,
        ))
    return result


class LotVolumeDiscrepancy(BaseModel):
    lot_id: int
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    catalog_no: Optional[str]
    lot_no: str
    date_received: date
    recorded_ul: float
    standard_ul: float
    current_volume_ul: float
    verified: bool                 # if True, a correction leaves current volume alone


class StoreVolumeDiscrepancy(BaseModel):
    store_id: int
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    catalog_no: Optional[str]
    lot_no: str
    quantity: int
    recorded_ul: float
    standard_ul: float


class AntibodyNoVolume(BaseModel):
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    catalog_no: Optional[str]


class VolumeDiscrepancyReport(BaseModel):
    lots: List[LotVolumeDiscrepancy]
    store: List[StoreVolumeDiscrepancy]
    antibodies_without_volume: List[AntibodyNoVolume]


@router.get("/volume-discrepancies", response_model=VolumeDiscrepancyReport)
def volume_discrepancies(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Active lots and store vials whose recorded starting volume differs from the
    antibody master's standard vial volume (and was not recorded as a deliberate
    override), plus active antibodies with no standard volume set."""
    abs_ = {a.id: a for a in session.exec(select(Antibody).where(Antibody.active == True)).all()}  # noqa: E712
    fc_name = lambda a: a.fluorochrome.name if a.fluorochrome else None  # noqa: E731

    lots_out: List[LotVolumeDiscrepancy] = []
    for lot in session.exec(select(StockLot).where(StockLot.active == True)).all():  # noqa: E712
        ab = abs_.get(lot.antibody_id)
        if not ab or ab.vial_volume_ul is None or is_overridden(lot.notes):
            continue
        if abs(lot.initial_volume_ul - ab.vial_volume_ul) <= TOLERANCE_UL:
            continue
        lots_out.append(LotVolumeDiscrepancy(
            lot_id=lot.id, antibody_id=ab.id, antibody_name=ab.name, fluorochrome=fc_name(ab),
            catalog_no=ab.catalog_no, lot_no=lot.lot_no, date_received=lot.date_received,
            recorded_ul=lot.initial_volume_ul, standard_ul=ab.vial_volume_ul,
            current_volume_ul=round(lot.current_volume_ul, 2),
            verified=lot.last_verified_date is not None,
        ))

    store_out: List[StoreVolumeDiscrepancy] = []
    for ss in session.exec(select(StoreStock).where(StoreStock.quantity > 0)).all():
        ab = abs_.get(ss.antibody_id)
        if not ab or ab.vial_volume_ul is None or is_overridden(ss.notes):
            continue
        if abs(ss.volume_per_vial_ul - ab.vial_volume_ul) <= TOLERANCE_UL:
            continue
        store_out.append(StoreVolumeDiscrepancy(
            store_id=ss.id, antibody_id=ab.id, antibody_name=ab.name, fluorochrome=fc_name(ab),
            catalog_no=ab.catalog_no, lot_no=ss.lot_no, quantity=ss.quantity,
            recorded_ul=ss.volume_per_vial_ul, standard_ul=ab.vial_volume_ul,
        ))

    missing = [
        AntibodyNoVolume(antibody_id=a.id, antibody_name=a.name, fluorochrome=fc_name(a), catalog_no=a.catalog_no)
        for a in sorted(abs_.values(), key=lambda a: a.name.lower()) if a.vial_volume_ul is None
    ]
    return VolumeDiscrepancyReport(lots=lots_out, store=store_out, antibodies_without_volume=missing)


class CorrectStartVolume(BaseModel):
    correct_initial_volume_ul: float
    reason: str


@router.post("/{lot_id}/correct-start-volume", response_model=StockLotRead)
def correct_start_volume(
    lot_id: int,
    payload: CorrectStartVolume,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """
    Fix a starting volume that was entered wrongly.

    The remaining volume is shifted by the same amount (it was derived from the
    wrong start), EXCEPT when the lot has been physically verified: verification
    re-anchors the remaining volume to a measurement, so only the starting
    volume is corrected then. Recorded in the lot notes.
    """
    lot = session.get(StockLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    if payload.correct_initial_volume_ul <= 0:
        raise HTTPException(status_code=400, detail="Volume must be greater than 0 µl")
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required")

    old_start, old_current = lot.initial_volume_ul, lot.current_volume_ul
    if abs(payload.correct_initial_volume_ul - old_start) <= TOLERANCE_UL:
        # Recorded volume confirmed as right (genuinely non-standard vial):
        # record it as a deliberate override so it stops being flagged.
        ab = session.get(Antibody, lot.antibody_id)
        std = f"standard {ab.vial_volume_ul:g} µl, " if ab and ab.vial_volume_ul is not None else ""
        lot.notes = append_note(lot.notes, (
            f"{OVERRIDE_TAG} {date.today()} by {current_user.username}: {std}recorded "
            f"{old_start:g} µl confirmed correct — {payload.reason.strip()}"))
        session.add(lot)
        session.commit()
        session.refresh(lot)
        return _enrich_lot(lot, session)
    delta = payload.correct_initial_volume_ul - old_start
    lot.initial_volume_ul = payload.correct_initial_volume_ul
    if lot.last_verified_date is None:
        lot.current_volume_ul = max(0.0, round(old_current + delta, 3))
        how = f"remaining {old_current:g}→{lot.current_volume_ul:g} µl"
    else:
        how = f"remaining unchanged ({old_current:g} µl, verified {lot.last_verified_date})"
    note = (f"{CORRECTION_TAG} {date.today()} by {current_user.username}: start "
            f"{old_start:g}→{lot.initial_volume_ul:g} µl, {how} — {payload.reason.strip()}")
    lot.notes = append_note(lot.notes, note)
    session.add(lot)
    session.commit()
    session.refresh(lot)
    return _enrich_lot(lot, session)


@router.get("/{lot_id}", response_model=StockLotRead)
def get_lot(
    lot_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    lot = session.get(StockLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return _enrich_lot(lot, session)


@router.post("/bulk", response_model=list[StockLotRead])
def bulk_receive(
    payloads: list[StockLotCreate],
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """Receive multiple lots in one request. Skips rows with missing antibody.

    Every row's volume is checked BEFORE anything is saved, so one bad row
    rejects the batch instead of leaving it half-received."""
    prepared = []
    errors = []
    for i, payload in enumerate(payloads, start=1):
        ab = session.get(Antibody, payload.antibody_id)
        if not ab:
            continue
        try:
            prepared.append(_new_lot(payload, ab))
        except ValueError as e:
            errors.append(f"Row {i}: {e}")
    if errors:
        raise HTTPException(status_code=400, detail=" | ".join(errors))

    created = []
    for lot in prepared:
        session.add(lot)
        session.flush()
        ensure_shipment_verification(
            antibody_id=lot.antibody_id, shipment_id=lot.shipment_id, lot_no=lot.lot_no,
            received=lot.date_received, session=session, user_id=current_user.id,
        )
        session.commit()
        session.refresh(lot)
        created.append(_enrich_lot(lot, session))
    return created


@router.post("/", response_model=StockLotRead)
def receive_lot(
    payload: StockLotCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    ab = session.get(Antibody, payload.antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    try:
        lot = _new_lot(payload, ab)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.add(lot)
    session.flush()
    ensure_shipment_verification(
        antibody_id=lot.antibody_id, shipment_id=lot.shipment_id, lot_no=lot.lot_no,
        received=lot.date_received, session=session, user_id=current_user.id,
    )
    session.commit()
    session.refresh(lot)
    return _enrich_lot(lot, session)


@router.post("/{lot_id}/verify", response_model=StockLotRead)
def verify_lot(
    lot_id: int,
    payload: VerifyPayload,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """
    Physical volume verification. Updates current_volume_ul to the measured value.
    Accepts minor negative corrections (tube loss during pipetting verification
    is clinically expected — don't block it).
    """
    if payload.verified_volume_ul < 0:
        raise HTTPException(status_code=400, detail="Volume cannot be negative")

    lot = session.get(StockLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    vlog = verify_stock_volume(
        lot=lot,
        verified_volume_ul=payload.verified_volume_ul,
        session=session,
        verified_by_user_id=current_user.id,          # now required
        measurement_method=payload.measurement_method,
        pipette_increment_ul=payload.pipette_increment_ul,
        verification_cycle=payload.verification_cycle,
    )
    session.commit()
    session.refresh(lot)
    return _enrich_lot(lot, session)


@router.patch("/{lot_id}/open", response_model=StockLotRead)
def mark_opened(
    lot_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_technologist_or_admin),
):
    """Record the date a vial was first opened."""
    lot = session.get(StockLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    lot.date_opened = date.today()
    session.add(lot)
    session.commit()
    session.refresh(lot)
    return _enrich_lot(lot, session)


@router.delete("/{lot_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_stock_lot(lot_id: int, session: Session = Depends(get_session)):
    """
    Hard-delete a stock lot. Blocked if the lot has any consumption history,
    since that would orphan FIFO records. Zero-volume lots with no history
    (e.g. dummy/placeholder entries) are deleted cleanly.
    """
    from app.models import ConsumptionLog, VerificationLog
    from sqlmodel import select

    lot = session.get(StockLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    if session.exec(select(ConsumptionLog).where(ConsumptionLog.stock_lot_id == lot_id)).first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: lot has consumption history. Set volume to 0 and deactivate instead.",
        )
    if session.exec(select(VerificationLog).where(VerificationLog.stock_lot_id == lot_id)).first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: lot has verification records attached.",
        )

    session.delete(lot)
    session.commit()
