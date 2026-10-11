"""routers/store_stock.py — Stockroom vial management."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin, require_technologist_or_admin
from app.database import get_session
from app.models import Antibody, Fluorochrome, StockLot, StoreStock, User
from app.services.vial_volume import append_note, resolve_vial_volume
from app.services.shipments import (
    display_status, ensure_shipment_verification, get_verification, normalise_shipment_id,
)

router = APIRouter(prefix="/api/store-stock", tags=["store-stock"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StoreStockCreate(BaseModel):
    antibody_id: int
    lot_no: str
    vendor: Optional[str] = None
    catalog_no: Optional[str] = None
    quantity: int = 1
    # Omit to use the antibody's standard vial volume (no more silent 500 µl default).
    volume_per_vial_ul: Optional[float] = None
    volume_override_reason: Optional[str] = None
    received_date: date
    expiry_date: Optional[date] = None
    shipment_id: Optional[str] = None
    notes: Optional[str] = None


class StoreStockUpdate(BaseModel):
    quantity: Optional[int] = None
    volume_per_vial_ul: Optional[float] = None
    volume_override_reason: Optional[str] = None
    expiry_date: Optional[date] = None
    shipment_id: Optional[str] = None
    notes: Optional[str] = None


class StoreStockRead(BaseModel):
    id: int
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    vendor: Optional[str]
    catalog_no: Optional[str]
    lot_no: str
    quantity: int
    volume_per_vial_ul: float
    total_store_ul: float          # quantity × volume_per_vial_ul
    received_date: date
    expiry_date: Optional[date]
    shipment_id: Optional[str]
    notes: Optional[str]
    # Shipment-to-shipment verification for this antibody + shipment, if any
    verification_id: Optional[int] = None
    verification_status: Optional[str] = None   # pending | overdue | acceptable | not_acceptable
    verification_triggered: bool = False        # True only on the receive call that raised it


def _enrich(ss: StoreStock, session: Session, triggered: bool = False) -> StoreStockRead:
    ab = session.get(Antibody, ss.antibody_id)
    v = get_verification(ss.antibody_id, ss.shipment_id, session)
    fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab and ab.fluorochrome_id else None
    return StoreStockRead(
        id=ss.id,
        antibody_id=ss.antibody_id,
        antibody_name=ab.name if ab else "Unknown",
        fluorochrome=fc.name if fc else None,
        vendor=ss.vendor,
        catalog_no=ss.catalog_no,
        lot_no=ss.lot_no,
        quantity=ss.quantity,
        volume_per_vial_ul=ss.volume_per_vial_ul,
        total_store_ul=round(ss.quantity * ss.volume_per_vial_ul, 1),
        received_date=ss.received_date,
        expiry_date=ss.expiry_date,
        shipment_id=ss.shipment_id,
        notes=ss.notes,
        verification_id=v.id if v else None,
        verification_status=display_status(v),
        verification_triggered=triggered,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[StoreStockRead])
def list_store_stock(
    antibody_id: Optional[int] = None,
    in_stock_only: bool = True,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(StoreStock).order_by(StoreStock.expiry_date)
    if antibody_id:
        q = q.where(StoreStock.antibody_id == antibody_id)
    if in_stock_only:
        q = q.where(StoreStock.quantity > 0)
    rows = session.exec(q).all()
    return [_enrich(r, session) for r in rows]


@router.post("/", response_model=StoreStockRead)
def receive_store_stock(
    payload: StoreStockCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    ab = session.get(Antibody, payload.antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")
    try:
        volume, note = resolve_vial_volume(ab, payload.volume_per_vial_ul, payload.volume_override_reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = payload.model_dump(exclude={"volume_per_vial_ul", "volume_override_reason"})
    data["shipment_id"] = normalise_shipment_id(data.get("shipment_id"))
    # Catalogue number / vendor default from the antibody master
    data["catalog_no"] = data.get("catalog_no") or ab.catalog_no
    data["vendor"] = data.get("vendor") or ab.vendor
    data["notes"] = append_note(data.get("notes"), note, limit=256)
    ss = StoreStock(**data, volume_per_vial_ul=volume)
    session.add(ss)
    session.flush()
    _, created = ensure_shipment_verification(
        antibody_id=ss.antibody_id,
        shipment_id=ss.shipment_id,
        lot_no=ss.lot_no,
        received=ss.received_date,
        session=session,
        user_id=current_user.id,
    )
    session.commit()
    session.refresh(ss)
    return _enrich(ss, session, triggered=created)


@router.patch("/{ss_id}", response_model=StoreStockRead)
def update_store_stock(
    ss_id: int,
    payload: StoreStockUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    ss = session.get(StoreStock, ss_id)
    if not ss:
        raise HTTPException(status_code=404, detail="Store stock entry not found")
    data = payload.model_dump(exclude_none=True)
    reason = data.pop("volume_override_reason", None)
    if "volume_per_vial_ul" in data:
        ab = session.get(Antibody, ss.antibody_id)
        try:
            volume, note = resolve_vial_volume(ab, data["volume_per_vial_ul"], reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        data["volume_per_vial_ul"] = volume
        if note:
            data["notes"] = append_note(data.get("notes", ss.notes), note, limit=256)
    if "shipment_id" in data:
        data["shipment_id"] = normalise_shipment_id(data["shipment_id"])
    old_shipment = ss.shipment_id
    for k, v in data.items():
        setattr(ss, k, v)
    session.add(ss)
    session.flush()
    created = False
    if ss.shipment_id and ss.shipment_id != old_shipment:
        # Tagging / re-tagging a row is a shipment receipt as far as QC is concerned
        _, created = ensure_shipment_verification(
            antibody_id=ss.antibody_id,
            shipment_id=ss.shipment_id,
            lot_no=ss.lot_no,
            received=ss.received_date,
            session=session,
            user_id=current_user.id,
        )
    session.commit()
    session.refresh(ss)
    return _enrich(ss, session, triggered=created)


@router.post("/{ss_id}/open-vial", response_model=StoreStockRead)
def open_vial(
    ss_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """
    Transfer one vial from store stock to open inventory.
    Decrements store quantity by 1 and creates a StockLot.
    """
    ss = session.get(StoreStock, ss_id)
    if not ss:
        raise HTTPException(status_code=404, detail="Store stock entry not found")
    if ss.quantity < 1:
        raise HTTPException(status_code=409, detail="No vials remaining in store for this lot")

    ss.quantity -= 1
    # The store record's volume is used as recorded. Standard-volume checks apply
    # prospectively (at receipt, from v0.8.1 on); records made before that are
    # left untouched — Antibodies > Volume check lists them for manual review.
    volume = ss.volume_per_vial_ul
    # (vendor / catalog_no were previously passed here too, but StockLot has no
    # such columns and SQLModel silently dropped them.)
    lot = StockLot(
        antibody_id=ss.antibody_id,
        lot_no=ss.lot_no,
        initial_volume_ul=volume,
        current_volume_ul=volume,
        date_received=date.today(),
        expiry_date=ss.expiry_date,
        shipment_id=ss.shipment_id,
    )
    session.add(lot)
    session.add(ss)
    session.commit()
    session.refresh(ss)
    return _enrich(ss, session)


@router.delete("/{ss_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_store_stock(ss_id: int, session: Session = Depends(get_session)):
    ss = session.get(StoreStock, ss_id)
    if not ss:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(ss)
    session.commit()


@router.get("/check/{antibody_id}")
def check_store_stock(
    antibody_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Returns whether the antibody has any store stock records (for receive-lot warning)."""
    has_stock = session.exec(
        select(StoreStock)
        .where(StoreStock.antibody_id == antibody_id)
        .where(StoreStock.quantity > 0)
    ).first() is not None
    return {"has_store_stock": has_stock}
