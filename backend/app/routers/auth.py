"""routers/auth.py — Token endpoint (OAuth2 password flow)."""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
)
from app.database import get_session
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str


class UserRead(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    active: bool


@router.post("/token", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    user = authenticate_user(form_data.username, form_data.password, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(
        access_token=token,
        token_type="bearer",
        role=user.role,
        username=user.username,
    )


STATION_TOKEN_DAYS = 30


@router.post("/station-token", response_model=Token)
def station_token(current_user: User = Depends(get_current_user)):
    """Long-lived session for the bench tablet, which runs unattended all day.
    Only issued to technologist logins: a 30-day admin session left on a shared
    tablet would hand full management rights to anyone who picks it up."""
    if current_user.role != "technologist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign the station in with a technologist login, not an admin one",
        )
    token = create_access_token(
        data={"sub": current_user.username, "role": current_user.role, "station": True},
        expires_delta=timedelta(days=STATION_TOKEN_DAYS),
    )
    return Token(access_token=token, token_type="bearer",
                 role=current_user.role, username=current_user.username)


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupRequest(BaseModel):
    username: str
    email: Optional[str] = None
    password: str


@router.get("/setup-status", response_model=SetupStatus)
def setup_status(session: Session = Depends(get_session)):
    """True while no users exist — the operator must create the first admin."""
    return SetupStatus(needs_setup=session.exec(select(User)).first() is None)


@router.post("/setup", response_model=Token, status_code=201)
def setup(payload: SetupRequest, session: Session = Depends(get_session)):
    """First-run admin creation. Refuses once any user already exists."""
    if session.exec(select(User)).first() is not None:
        raise HTTPException(status_code=409, detail="Setup already completed")

    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )
    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=username,
        email=payload.email or None,
        hashed_password=hash_password(payload.password),
        role="admin",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(
        access_token=token,
        token_type="bearer",
        role=user.role,
        username=user.username,
    )
