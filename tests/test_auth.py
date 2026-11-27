import time

import jwt
import pytest
from fastapi import HTTPException

import auth


def test_password_hash_roundtrip():
    stored = auth.hash_password("a-long-enough-password")

    assert stored.startswith("pbkdf2_sha256$")
    assert auth.verify_password("a-long-enough-password", stored)
    assert not auth.verify_password("wrong-password-value", stored)


def test_password_hashes_are_salted():
    first = auth.hash_password("a-long-enough-password")
    second = auth.hash_password("a-long-enough-password")

    assert first != second


def test_short_password_rejected():
    with pytest.raises(ValueError):
        auth.hash_password("short")


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "not-a-hash",
        "pbkdf2_sha256$10$salt$digest",  # iteration count below the floor
        "md5$600000$c2FsdA$ZGlnZXN0",  # unsupported algorithm
    ],
)
def test_verify_password_rejects_malformed_hashes(stored):
    assert not auth.verify_password("anything-at-all-1", stored)


def test_token_roundtrip_contains_required_claims():
    payload = auth.verify_access_token(auth.create_access_token("alice", 7))

    assert payload["sub"] == "alice"
    assert payload["uid"] == 7
    assert payload["iss"] == auth.TOKEN_ISSUER
    assert payload["jti"]


def test_each_token_has_a_unique_jti():
    first = auth.verify_access_token(auth.create_access_token("alice", 1))
    second = auth.verify_access_token(auth.create_access_token("alice", 1))

    assert first["jti"] != second["jti"]


def _forge(claims: dict, secret: str | None = None, algorithm: str = "HS256"):
    return jwt.encode(claims, secret or auth._get_secret(), algorithm=algorithm)


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "sub": "alice",
        "iss": auth.TOKEN_ISSUER,
        "iat": now,
        "exp": now + 600,
        "jti": "abc123",
    }
    claims.update(overrides)
    return claims


def test_expired_token_rejected():
    token = _forge(_claims(iat=1, exp=2))

    with pytest.raises(HTTPException) as error:
        auth.verify_access_token(token)

    assert error.value.status_code == 401


def test_wrong_signature_rejected():
    token = _forge(_claims(), secret="a-different-secret-" + "y" * 30)

    with pytest.raises(HTTPException) as error:
        auth.verify_access_token(token)

    assert error.value.status_code == 401


def test_wrong_issuer_rejected():
    with pytest.raises(HTTPException):
        auth.verify_access_token(_forge(_claims(iss="someone-else")))


def test_missing_jti_rejected():
    claims = _claims()
    del claims["jti"]

    with pytest.raises(HTTPException):
        auth.verify_access_token(_forge(claims))


def test_overlong_lifetime_rejected():
    now = int(time.time())

    with pytest.raises(HTTPException):
        auth.verify_access_token(_forge(_claims(iat=now, exp=now + 86_400)))


def test_unsigned_token_rejected():
    token = jwt.encode(_claims(), key=None, algorithm="none")

    with pytest.raises(HTTPException):
        auth.verify_access_token(token)


def test_short_secret_is_refused(monkeypatch):
    monkeypatch.setenv("RAG_AUTH_SECRET", "too-short")

    with pytest.raises(RuntimeError):
        auth.create_access_token("alice", 1)
