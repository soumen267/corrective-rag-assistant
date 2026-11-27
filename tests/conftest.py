"""Shared test configuration.

Environment variables are set BEFORE any application module is imported so the
tests never read the developer's real .env (python-dotenv does not override
variables that are already set) and never touch the real MySQL database.
"""

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(_type, _compiler, **_kwargs):
    # SQLite only auto-increments an INTEGER primary key; MySQL keeps BIGINT.
    return "INTEGER"


os.environ["RAG_AUTH_SECRET"] = "test-secret-" + "x" * 40
os.environ["RAG_ADMIN_USERNAME"] = "legacy_admin"
os.environ["MYSQL_DATABASE"] = "rag_test_unused"
os.environ["MYSQL_USER"] = "unused"
os.environ["MYSQL_PASSWORD"] = ""

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))


@pytest.fixture()
def sqlite_session_factory():
    """In-memory SQLite stand-in for MySQL with all application tables."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import chat_models  # noqa: F401  (register tables on Base)
    import document_models  # noqa: F401
    import token_store  # noqa: F401
    import user_models  # noqa: F401
    from database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    yield factory

    engine.dispose()


@pytest.fixture()
def client(sqlite_session_factory, monkeypatch, tmp_path):
    """FastAPI test client backed by SQLite and a temporary data directory."""
    from fastapi.testclient import TestClient

    import api
    import auth_routes
    import knowledge_base
    from database import get_db

    def override_get_db():
        db = sqlite_session_factory()
        try:
            yield db
        finally:
            db.close()

    api.app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(api, "SessionLocal", sqlite_session_factory)
    monkeypatch.setattr(knowledge_base, "DATA_DIRECTORY", tmp_path / "data")

    # Login rate-limit state is module-global; isolate every test.
    auth_routes._login_attempts.clear()
    auth_routes._login_blocked_until.clear()

    # No `with` block: the MySQL lifespan hook must not run in tests.
    yield TestClient(api.app)

    api.app.dependency_overrides.clear()


@pytest.fixture()
def make_user(sqlite_session_factory):
    """Create a database user and return (user, password)."""
    from auth import hash_password
    from user_models import User

    def _make_user(username="alice", role="user", active=True):
        password = "correct-horse-battery"
        with sqlite_session_factory() as db:
            user = User(
                username=username,
                email=f"{username}@example.com",
                password_hash=hash_password(password),
                role=role,
                is_active=active,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user, password

    return _make_user


@pytest.fixture()
def auth_headers(client, make_user):
    """Return a function that logs in a user and yields bearer headers."""

    def _auth_headers(username="alice", role="user"):
        _user, password = make_user(username=username, role=role)
        response = client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _auth_headers
