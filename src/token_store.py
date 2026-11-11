from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

try:
    from .database import Base, engine
except ImportError:
    from database import Base, engine


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(128), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def init_token_store() -> None:
    """Create only the revoked_tokens table if it does not exist."""
    RevokedToken.__table__.create(bind=engine, checkfirst=True)


def revoke_token(db: Session, jti: str, expires_at: datetime) -> None:
    """Save a revoked JWT ID until its original expiry time."""
    if not isinstance(jti, str) or not jti.strip() or len(jti) > 128:
        raise ValueError("A valid JWT ID (jti) is required.")

    db.add(
        RevokedToken(
            jti=jti,
            expires_at=_utc_naive(expires_at),
            revoked_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Revoking the same token more than once is harmless.
        db.rollback()


def is_token_revoked(db: Session, jti: Optional[str]) -> bool:
    """Check whether a JWT ID exists in the revocation table."""
    if not jti:
        return True

    statement = select(RevokedToken.jti).where(RevokedToken.jti == jti).limit(1)
    return db.execute(statement).scalar_one_or_none() is not None


def cleanup_expired_tokens(db: Session) -> int:
    """Remove expired revocation rows and return the number deleted."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = db.execute(delete(RevokedToken).where(RevokedToken.expires_at <= now))
    db.commit()
    return max(result.rowcount or 0, 0)
