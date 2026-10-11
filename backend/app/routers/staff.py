"""
routers/staff.py — master list of pathologists and technologists referenced on
sample orders. Admin-maintained under Lab Settings. Separate from login users.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin
from app.database import get_session
from app.models import SampleOrder, Staff, User

router = APIRouter(prefix="/api/staff", tags=["staff"])

VALID_ROLES = ("pathologist", "technologist")


class StaffCreate(BaseModel):
    name: str
    role: str = "technologist"
    initials: Optional[str] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    initials: Optional[str] = None
    active: Optional[bool] = None


class StaffRead(BaseModel):
    id: int
    name: str
    role: str
    initials: Optional[str]
    active: bool


def _read(s: Staff) -> StaffRead:
    return StaffRead(id=s.id, name=s.name, role=s.role, initials=s.initials, active=s.active)


@router.get("/", response_model=List[StaffRead])
def list_staff(
    role: Optional[str] = None,
    active_only: bool = True,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(Staff)
    if role:
        q = q.where(Staff.role == role)
    if active_only:
        q = q.where(Staff.active == True)  # noqa: E712
    rows = session.exec(q.order_by(Staff.role, Staff.name)).all()
    return [_read(s) for s in rows]


@router.post("/", response_model=StaffRead, dependencies=[Depends(require_admin)])
def create_staff(payload: StaffCreate, session: Session = Depends(get_session)):
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {VALID_ROLES}")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    s = Staff(name=payload.name.strip(), role=payload.role, initials=payload.initials or None)
    session.add(s)
    session.commit()
    session.refresh(s)
    return _read(s)


@router.patch("/{staff_id}", response_model=StaffRead, dependencies=[Depends(require_admin)])
def update_staff(staff_id: int, payload: StaffUpdate, session: Session = Depends(get_session)):
    s = session.get(Staff, staff_id)
    if not s:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if payload.role is not None and payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {VALID_ROLES}")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    session.add(s)
    session.commit()
    session.refresh(s)
    return _read(s)


@router.delete("/{staff_id}", dependencies=[Depends(require_admin)])
def delete_staff(staff_id: int, session: Session = Depends(get_session)):
    s = session.get(Staff, staff_id)
    if not s:
        raise HTTPException(status_code=404, detail="Staff member not found")
    # Soft-delete if referenced by any order, else hard-delete
    referenced = session.exec(
        select(SampleOrder).where(
            (SampleOrder.requesting_pathologist_id == staff_id)
            | (SampleOrder.processing_technologist_id == staff_id)
        )
    ).first()
    if referenced:
        s.active = False
        session.add(s)
        session.commit()
        return {"deactivated": True, "reason": "referenced by existing orders"}
    session.delete(s)
    session.commit()
    return {"deleted": True}
