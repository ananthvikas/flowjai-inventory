"""routers/fluorochromes.py — CRUD for fluorochromes (admin write, all read)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin
from app.database import get_session
from app.models import Fluorochrome, User

router = APIRouter(prefix="/api/fluorochromes", tags=["fluorochromes"])


class FluorochromeCreate(BaseModel):
    name: str
    excitation_nm: Optional[int] = None
    emission_nm: Optional[int] = None
    laser: Optional[str] = None


class FluorochromeRead(BaseModel):
    id: int
    name: str
    excitation_nm: Optional[int]
    emission_nm: Optional[int]
    laser: Optional[str]


@router.get("/", response_model=List[FluorochromeRead])
def list_fluorochromes(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    return session.exec(select(Fluorochrome).order_by(Fluorochrome.name)).all()


@router.post("/", response_model=FluorochromeRead, dependencies=[Depends(require_admin)])
def create_fluorochrome(payload: FluorochromeCreate, session: Session = Depends(get_session)):
    existing = session.exec(
        select(Fluorochrome).where(Fluorochrome.name == payload.name)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Fluorochrome name already exists")

    fc = Fluorochrome(**payload.model_dump())
    session.add(fc)
    session.commit()
    session.refresh(fc)
    return fc


@router.patch("/{fc_id}", response_model=FluorochromeRead, dependencies=[Depends(require_admin)])
def update_fluorochrome(
    fc_id: int, payload: FluorochromeCreate, session: Session = Depends(get_session)
):
    fc = session.get(Fluorochrome, fc_id)
    if not fc:
        raise HTTPException(status_code=404, detail="Fluorochrome not found")

    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(fc, k, v)

    session.add(fc)
    session.commit()
    session.refresh(fc)
    return fc


@router.delete("/{fc_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_fluorochrome(fc_id: int, session: Session = Depends(get_session)):
    fc = session.get(Fluorochrome, fc_id)
    if not fc:
        raise HTTPException(status_code=404, detail="Fluorochrome not found")
    session.delete(fc)
    session.commit()
