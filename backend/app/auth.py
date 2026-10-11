"""
auth.py — JWT token creation/verification, password hashing, role-based access control.

Two roles:
  admin       — full CRUD on all resources
  technologist — stock updates, test log entry, alert acknowledgement, read-only on config

Role enforcement is via FastAPI dependencies injected at the router level.
Never enforce role in a service — services are role-agnostic so tests can call them directly.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Suppress passlib's noisy bcrypt version warning (harmless with bcrypt==4.0.1)
logging.getLogger('passlib').setLevel(logging.ERROR)

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.database import get_session
from app.models import User

def _load_or_create_secret_key() -> str:
    """Return a stable per-install signing key, generating and persisting one
    next to the database on first run. Never ships a hardcoded default."""
    key = os.getenv("SECRET_KEY")
    if key:
        return key

    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url[len("sqlite:///"):])
        key_dir = db_path.parent if str(db_path.parent) else Path(".")
    else:
        key_dir = Path("data")

    key_dir.mkdir(parents=True, exist_ok=True)
    key_file = key_dir / ".secret_key"
    if key_file.exists():
        existing = key_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    new_key = secrets.token_hex(32)
    key_file.write_text(new_key, encoding="utf-8")
    return new_key


SECRET_KEY = _load_or_create_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = session.exec(select(User).where(User.username == username)).first()
    if user is None or not user.active:
        raise credentials_exc
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Admin (or service) access — both roles have full management rights."""
    if current_user.role not in ("admin", "service"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_service(current_user: User = Depends(get_current_user)) -> User:
    """Service-only access — for validation screens not visible to regular admins."""
    if current_user.role != "service":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service access required",
        )
    return current_user


def require_technologist_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Allows both roles — effectively just requires authentication."""
    if current_user.role not in ("admin", "technologist"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return current_user


def authenticate_user(username: str, password: str, session: Session) -> Optional[User]:
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        return None
    if not user.active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
