import pytest

import api


def test_cors_defaults_to_local_frontend(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)

    assert api.get_cors_origins() == [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ]


def test_cors_origins_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        " https://app.example.com , ,https://admin.example.com ",
    )

    assert api.get_cors_origins() == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_wildcard_cors_origin_is_refused(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example.com,*")

    with pytest.raises(RuntimeError):
        api.get_cors_origins()


def test_utc_now_is_naive_utc():
    from datetime import datetime, timezone

    value = api.utc_now()
    reference = datetime.now(timezone.utc).replace(tzinfo=None)

    assert value.tzinfo is None
    assert abs((reference - value).total_seconds()) < 5
