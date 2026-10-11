"""routers/orders.py — Purchase order tracking."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin, require_technologist_or_admin
from app.database import get_session
from app.models import Antibody, Order, StockLot, User
from app.services.shipments import ensure_shipment_verification, normalise_shipment_id
from app.services.vial_volume import append_note, resolve_vial_volume

router = APIRouter(prefix="/api/orders", tags=["orders"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class OrderCreate(BaseModel):
    antibody_id: int
    quantity_vials: int
    # Omit to use the antibody's standard vial volume
    volume_per_vial_ul: Optional[float] = None
    volume_override_reason: Optional[str] = None
    order_date: date
    expected_delivery_date: Optional[date] = None
    po_number: Optional[str] = None
    notes: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[str] = None           # pending | delivered | cancelled
    expected_delivery_date: Optional[date] = None
    po_number: Optional[str] = None
    notes: Optional[str] = None


class OrderRead(BaseModel):
    id: int
    antibody_id: int
    antibody_name: str
    quantity_vials: int
    volume_per_vial_ul: float
    total_volume_ul: float
    order_date: date
    expected_delivery_date: Optional[date]
    status: str
    po_number: Optional[str]
    notes: Optional[str]
    created_by: int


class DeliverPayload(BaseModel):
    lot_no: str
    actual_volume_per_vial_ul: Optional[float] = None   # if different from ordered
    volume_override_reason: Optional[str] = None        # required if not the standard volume
    expiry_date: Optional[date] = None
    delivery_date: Optional[date] = None
    shipment_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich(order: Order, session: Session) -> OrderRead:
    ab = session.get(Antibody, order.antibody_id)
    return OrderRead(
        id=order.id,
        antibody_id=order.antibody_id,
        antibody_name=ab.name if ab else "unknown",
        quantity_vials=order.quantity_vials,
        volume_per_vial_ul=order.volume_per_vial_ul,
        total_volume_ul=order.quantity_vials * order.volume_per_vial_ul,
        order_date=order.order_date,
        expected_delivery_date=order.expected_delivery_date,
        status=order.status,
        po_number=order.po_number,
        notes=order.notes,
        created_by=order.created_by,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[OrderRead])
def list_orders(
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(Order).order_by(Order.order_date.desc())
    if status:
        q = q.where(Order.status == status)
    return [_enrich(o, session) for o in session.exec(q).all()]


@router.post("/", response_model=OrderRead, dependencies=[Depends(require_admin)])
def create_order(
    payload: OrderCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    ab = session.get(Antibody, payload.antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    try:
        volume, note = resolve_vial_volume(ab, payload.volume_per_vial_ul, payload.volume_override_reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = payload.model_dump(exclude={"volume_per_vial_ul", "volume_override_reason"})
    data["notes"] = append_note(data.get("notes"), note, limit=512)

    order = Order(
        **data,
        volume_per_vial_ul=volume,
        status="pending",
        created_by=current_user.id,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return _enrich(order, session)


@router.patch("/{order_id}", response_model=OrderRead, dependencies=[Depends(require_admin)])
def update_order(
    order_id: int, payload: OrderUpdate, session: Session = Depends(get_session)
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    valid_statuses = ("pending", "delivered", "cancelled")
    if payload.status and payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid_statuses}")

    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(order, k, v)

    session.add(order)
    session.commit()
    session.refresh(order)
    return _enrich(order, session)


@router.post("/{order_id}/deliver", response_model=OrderRead, dependencies=[Depends(require_admin)])
def mark_delivered(
    order_id: int,
    payload: DeliverPayload,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """
    Mark an order as delivered AND automatically create a StockLot for each vial.
    If actual_volume_per_vial_ul differs from ordered, the received volume is used.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == "delivered":
        raise HTTPException(status_code=409, detail="Order already marked delivered")
    if order.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot deliver a cancelled order")

    # The ordered volume may predate the standard-volume check (old 500 µl default),
    # so the delivered volume is checked against the antibody master here too.
    ab = session.get(Antibody, order.antibody_id)
    try:
        actual_vol, vol_note = resolve_vial_volume(
            ab, payload.actual_volume_per_vial_ul or order.volume_per_vial_ul,
            payload.volume_override_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    delivery_date = payload.delivery_date or date.today()
    shipment_id = normalise_shipment_id(payload.shipment_id)

    # Create one StockLot per vial in the order
    for i in range(order.quantity_vials):
        lot_suffix = f"-{i+1}" if order.quantity_vials > 1 else ""
        lot = StockLot(
            antibody_id=order.antibody_id,
            lot_no=f"{payload.lot_no}{lot_suffix}",
            initial_volume_ul=actual_vol,
            current_volume_ul=actual_vol,
            date_received=delivery_date,
            expiry_date=payload.expiry_date,
            shipment_id=shipment_id,
            notes=vol_note,
        )
        session.add(lot)
    session.flush()

    # Compare against the manufacturer lot number, not the per-vial "-n" suffix.
    ensure_shipment_verification(
        antibody_id=order.antibody_id, shipment_id=shipment_id, lot_no=payload.lot_no,
        received=delivery_date, session=session, user_id=current_user.id,
    )

    order.status = "delivered"
    shipment_note = f", shipment {shipment_id}" if shipment_id else ""
    order.notes = (order.notes or "") + f" | Delivered {delivery_date}, lot {payload.lot_no}{shipment_note}"
    session.add(order)
    session.commit()
    session.refresh(order)
    return _enrich(order, session)
