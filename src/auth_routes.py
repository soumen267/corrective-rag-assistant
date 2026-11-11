"""Authentication routes for legacy admin and MySQL-backed multi-user accounts.

User creation is admin-controlled. The existing .env admin can create the first
database admin account; database admins can then create additional accounts.
"""

import hmac
import os
import re
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .auth import (
        bearer_scheme,
        create_access_token,
        get_current_user,
        token_expiry_utc,
        verify_access_token,
        verify_password,
        hash_password,
    )
    from .database import get_db
    from .token_store import revoke_token
    from .user_models import User
except ImportError:
    from auth import (
        bearer_scheme,
        create_access_token,
        get_current_user,
        token_expiry_utc,
        verify_access_token,
        verify_password,
        hash_password,
    )
    from database import get_db
    from token_store import revoke_token
    from user_models import User


LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_BLOCK_SECONDS = 15 * 60
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_login_blocked_until: dict[str, float] = {}
_login_lock = Lock()

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_login_limit(client_key: str) -> None:
    now = time.monotonic()
    with _login_lock:
        blocked_until = _login_blocked_until.get(client_key, 0)
        if blocked_until > now:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Please try again later.",
                headers={"Retry-After": str(max(1, int(blocked_until - now)))},
            )
        attempts = _login_attempts[client_key]
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()


def _record_login_failure(client_key: str) -> None:
    now = time.monotonic()
    with _login_lock:
        attempts = _login_attempts[client_key]
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        attempts.append(now)
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            _login_blocked_until[client_key] = now + LOGIN_BLOCK_SECONDS
            attempts.clear()


def _clear_login_failures(client_key: str) -> None:
    with _login_lock:
        _login_attempts.pop(client_key, None)
        _login_blocked_until.pop(client_key, None)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(default="user", pattern=r"^(admin|user)$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


def _invalid_login() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username/email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    client_key = _client_key(request)
    _check_login_limit(client_key)

    # First check MySQL accounts (username OR email).
    user = (
        db.query(User)
        .filter(or_(User.username == payload.username, User.email == payload.username))
        .first()
    )

    if user is not None:
        password_valid = verify_password(payload.password, user.password_hash)
        if not user.is_active or not password_valid:
            _record_login_failure(client_key)
            raise _invalid_login()

        _clear_login_failures(client_key)
        return TokenResponse(
            access_token=create_access_token(user.username, int(user.id)),
            expires_in=3600,
        )

    # Keep the original .env admin login working for the first admin setup.
    configured_username = os.getenv("RAG_ADMIN_USERNAME", "")
    configured_password_hash = os.getenv("RAG_ADMIN_PASSWORD_HASH", "")
    username_valid = bool(configured_username) and hmac.compare_digest(
        payload.username, configured_username
    )
    password_valid = bool(configured_password_hash) and verify_password(
        payload.password, configured_password_hash
    )

    if not (username_valid and password_valid):
        _record_login_failure(client_key)
        raise _invalid_login()

    _clear_login_failures(client_key)
    return TokenResponse(
        access_token=create_access_token(configured_username),
        expires_in=3600,
    )


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    current_username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a user account. Only a legacy or database admin may do this."""
    legacy_admin = os.getenv("RAG_ADMIN_USERNAME", "")
    is_legacy_admin = bool(legacy_admin) and hmac.compare_digest(
        current_username, legacy_admin
    )

    current_record = db.query(User).filter(User.username == current_username).first()
    is_database_admin = (
        current_record is not None
        and current_record.is_active
        and current_record.role == "admin"
    )

    if not (is_legacy_admin or is_database_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator can create user accounts.",
        )

    existing = db.query(User).filter(
        or_(User.username == payload.username, User.email == payload.email)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered.",
        )

    try:
        user = User(
            username=payload.username,
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            role=payload.role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered.",
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "User created successfully.",
        "user": {
            "id": int(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": bool(user.is_active),
        },
    }


@router.get("/me")
def get_my_profile(
    current_username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current account profile without exposing password data."""
    user = db.query(User).filter(User.username == current_username).first()
    if user is not None:
        return {
            "id": int(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": bool(user.is_active),
        }

    # Legacy .env admin has no users-table row.
    return {
        "id": None,
        "username": current_username,
        "email": None,
        "role": "admin",
        "is_active": True,
    }


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """Revoke the current JWT until its original expiry time."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_access_token(credentials.credentials)
    revoke_token(db, payload["jti"], token_expiry_utc(payload))
    return {"message": "Successfully logged out."}
