"""JWT authentication helpers with MySQL-backed users and token revocation.

Compatibility:
- Existing admin tokens without a `uid` claim remain valid while the
  legacy RAG_ADMIN_USERNAME / RAG_ADMIN_PASSWORD_HASH settings are configured.
- Database-user tokens contain `uid` and are checked against the users table
  on every request, including the user's active status.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .token_store import is_token_revoked
    from .user_models import User
except ImportError:
    from database import get_db
    from token_store import is_token_revoked
    from user_models import User

load_dotenv()

TOKEN_LIFETIME_SECONDS = 60 * 60
PASSWORD_HASH_ITERATIONS = 600_000
TOKEN_ISSUER = "rag-learning"
TOKEN_ALGORITHM = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    """Create a PBKDF2 password hash."""
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}"
        f"${_b64encode(salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against the project's PBKDF2 password hash."""
    try:
        algorithm, iterations, salt_encoded, expected_encoded = stored_hash.split("$")
        iteration_count = int(iterations)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= iteration_count <= 2_000_000:
            return False
        salt = _b64decode(salt_encoded)
        expected = _b64decode(expected_encoded)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iteration_count
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _get_secret() -> str:
    secret = os.getenv("RAG_AUTH_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "RAG_AUTH_SECRET must contain at least 32 bytes. "
            "Generate a strong random secret and configure .env."
        )
    return secret


def create_access_token(username: str, user_id: int | None = None) -> str:
    """Create a signed JWT. Database users receive a numeric `uid` claim."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": username,
        "iss": TOKEN_ISSUER,
        "iat": now,
        "exp": now + TOKEN_LIFETIME_SECONDS,
        "jti": secrets.token_urlsafe(24),
    }
    if user_id is not None:
        payload["uid"] = int(user_id)
    token = jwt.encode(payload, _get_secret(), algorithm=TOKEN_ALGORITHM)
    return token.decode("utf-8") if isinstance(token, bytes) else token


def verify_access_token(token: str) -> dict[str, Any]:
    """Validate JWT signature, algorithm, issuer and required claims."""
    try:
        payload = jwt.decode(
            token,
            _get_secret(),
            algorithms=[TOKEN_ALGORITHM],
            issuer=TOKEN_ISSUER,
            options={"require": ["sub", "iss", "iat", "exp", "jti"]},
            leeway=30,
        )
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            raise jwt.InvalidTokenError("Invalid subject")
        if not isinstance(payload.get("jti"), str) or not payload["jti"]:
            raise jwt.InvalidTokenError("Invalid token identifier")
        if int(payload["exp"]) - int(payload["iat"]) > TOKEN_LIFETIME_SECONDS:
            raise jwt.InvalidTokenError("Token lifetime too long")
        if "uid" in payload and (
            isinstance(payload["uid"], bool)
            or not isinstance(payload["uid"], int)
            or payload["uid"] <= 0
        ):
            raise jwt.InvalidTokenError("Invalid user ID")
        return payload
    except RuntimeError:
        raise
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _unauthorized(detail: str = "Invalid or expired access token") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_record(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Return the active database user represented by a user JWT."""
    if credentials is None:
        raise _unauthorized("Authentication required.")

    payload = verify_access_token(credentials.credentials)
    if is_token_revoked(db, payload["jti"]):
        raise _unauthorized("Token has been revoked.")

    user_id = payload.get("uid")
    if user_id is None:
        raise _unauthorized("This token is not associated with a database user.")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise _unauthorized("User account is unavailable.")

    # Ensure the token subject still matches the account's current username.
    if not hmac.compare_digest(payload["sub"], user.username):
        raise _unauthorized("Token identity no longer matches the account.")

    return user


def get_current_user_id(
    current_user: User = Depends(get_current_user_record),
) -> int:
    """Return the authenticated database user's ID."""
    return int(current_user.id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> str:
    """Return username while supporting legacy admin and database-user JWTs.

    Existing API handlers currently expect a username string. Later ownership
    changes can use get_current_user_id or get_current_user_record.
    """
    if credentials is None:
        raise _unauthorized("Authentication required.")

    payload = verify_access_token(credentials.credentials)
    if is_token_revoked(db, payload["jti"]):
        raise _unauthorized("Token has been revoked.")

    user_id = payload.get("uid")
    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active:
            raise _unauthorized("User account is unavailable.")
        if not hmac.compare_digest(payload["sub"], user.username):
            raise _unauthorized("Token identity no longer matches the account.")
        return user.username

    # Backward compatibility for the existing environment-based admin login.
    configured_username = os.getenv("RAG_ADMIN_USERNAME", "")
    if not configured_username or not hmac.compare_digest(
        payload["sub"], configured_username
    ):
        raise _unauthorized()
    return configured_username


def token_expiry_utc(payload: dict[str, Any]) -> datetime:
    """Convert the JWT exp claim into a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
