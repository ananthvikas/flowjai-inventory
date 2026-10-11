"""routers/users.py - User management (admin only except password change)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, hash_password, require_admin, verify_password
from app.database import get_session
from app.models import User

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    role: str = "technologist"


class UserRead(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: str
    active: bool


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class AdminPasswordReset(BaseModel):
    new_password: str


@router.get("/", response_model=List[UserRead], dependencies=[Depends(require_admin)])
def list_users(session: Session = Depends(get_session)):
    return session.exec(select(User)).all()


@router.post("/", response_model=UserRead, dependencies=[Depends(require_admin)])
def create_user(payload: UserCreate, session: Session = Depends(get_session)):
    if payload.role not in ("admin", "technologist", "service"):
        raise HTTPException(status_code=400, detail="role must be 'admin', 'technologist', or 'service'")

    existing = session.exec(select(User).where(User.username == payload.username)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=payload.username,
        email=payload.email or None,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead, dependencies=[Depends(require_admin)])
def update_user(
    user_id: int, payload: UserUpdate, session: Session = Depends(get_session)
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.username is not None:
        # Check username not taken by someone else
        clash = session.exec(
            select(User).where(User.username == payload.username)
        ).first()
        if clash and clash.id != user_id:
            raise HTTPException(status_code=409, detail="Username already taken")
        user.username = payload.username

    if payload.email is not None:
        user.email = payload.email or None

    if payload.role is not None:
        if payload.role not in ("admin", "technologist", "service"):
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = payload.role

    if payload.active is not None:
        user.active = payload.active

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=204, dependencies=[Depends(require_admin)])
def admin_reset_password(
    user_id: int,
    payload: AdminPasswordReset,
    session: Session = Depends(get_session),
):
    """Admin resets any user's password without knowing the current one."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(payload.new_password)
    session.add(user)
    session.commit()


@router.post("/me/change-password", status_code=204)
def change_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(payload.new_password)
    session.add(current_user)
    session.commit()
