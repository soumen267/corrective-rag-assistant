"""Chat session ownership and persistence."""

import pytest
from fastapi import HTTPException

import api
import chat_models


@pytest.fixture()
def db_factory(sqlite_session_factory, monkeypatch):
    monkeypatch.setattr(api, "SessionLocal", sqlite_session_factory)
    return sqlite_session_factory


def test_new_session_is_created_and_owned(db_factory):
    session_id, history = api.get_or_create_session(None, "alice")

    assert session_id
    assert history.get_messages() == []

    with db_factory() as db:
        row = db.get(chat_models.ChatSession, session_id)
        assert row.owner_username == "alice"


def test_foreign_session_looks_like_a_missing_session(db_factory):
    session_id, _ = api.get_or_create_session(None, "alice")

    with pytest.raises(HTTPException) as foreign:
        api.get_or_create_session(session_id, "mallory")
    with pytest.raises(HTTPException) as missing:
        api.get_or_create_session("does-not-exist", "mallory")

    # Identical responses prevent session-id enumeration.
    assert foreign.value.status_code == missing.value.status_code == 404
    assert foreign.value.detail == missing.value.detail


def test_history_reloads_in_chronological_order(db_factory):
    session_id, _ = api.get_or_create_session(None, "alice")

    api.save_chat_exchange(session_id, "alice", "first question", "first answer")
    api.save_chat_exchange(session_id, "alice", "second question", "second answer")

    _, history = api.get_or_create_session(session_id, "alice")

    assert [m.content for m in history.get_messages()] == [
        "first question",
        "first answer",
        "second question",
        "second answer",
    ]


def test_only_the_latest_ten_messages_are_loaded(db_factory):
    session_id, _ = api.get_or_create_session(None, "alice")

    for number in range(8):
        api.save_chat_exchange(session_id, "alice", f"q{number}", f"a{number}")

    _, history = api.get_or_create_session(session_id, "alice")
    contents = [m.content for m in history.get_messages()]

    assert len(contents) == 10
    assert contents[0] == "q3"
    assert contents[-1] == "a7"


def test_cannot_save_into_another_users_session(db_factory):
    session_id, _ = api.get_or_create_session(None, "alice")

    with pytest.raises(HTTPException) as error:
        api.save_chat_exchange(session_id, "mallory", "hi", "hello")

    assert error.value.status_code == 404


def test_clear_session_endpoint_is_owner_scoped(client, auth_headers, make_user):
    alice_headers = auth_headers("alice")
    session_id, _ = api.get_or_create_session(None, "alice")
    api.save_chat_exchange(session_id, "alice", "q", "a")

    make_user("mallory")
    token = client.post(
        "/auth/login",
        json={"username": "mallory", "password": "correct-horse-battery"},
    ).json()["access_token"]

    denied = client.delete(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    allowed = client.delete(f"/sessions/{session_id}", headers=alice_headers)

    assert denied.status_code == 404
    assert allowed.status_code == 200

    _, history = api.get_or_create_session(session_id, "alice")
    assert history.get_messages() == []


def test_chat_rejects_blank_questions(client, auth_headers):
    headers = auth_headers("alice")

    assert client.post("/chat", headers=headers, json={"question": ""}).status_code == 422
    assert client.post("/chat", headers=headers, json={"question": "   "}).status_code == 422


def test_chat_rejects_overlong_questions(client, auth_headers):
    headers = auth_headers("alice")

    response = client.post(
        "/chat", headers=headers, json={"question": "x" * 2001}
    )

    assert response.status_code == 422


def test_chat_endpoint_returns_answer_and_persists_exchange(
    client, auth_headers, monkeypatch
):
    from citations import Citation

    headers = auth_headers("alice")
    citation = Citation(
        source="data/x.md",
        file_name="x.md",
        file_type="md",
        page=None,
        chunk_id="c1",
        relevance_score=0.9,
        excerpt="excerpt",
    )

    def fake_ask(question, history, owner_id):
        assert owner_id == "alice"  # retrieval is scoped to the caller
        return "The answer [Source 1]", [citation]

    monkeypatch.setattr(api, "ask_with_graph", fake_ask)

    response = client.post("/chat", headers=headers, json={"question": "Q?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "The answer [Source 1]"
    assert body["sources"][0]["chunk_id"] == "c1"

    _, history = api.get_or_create_session(body["session_id"], "alice")
    assert [m.role for m in history.get_messages()] == ["user", "assistant"]


def test_chat_failure_returns_generic_500(client, auth_headers, monkeypatch):
    headers = auth_headers("alice")

    def boom(**_kwargs):
        raise RuntimeError("ollama connection refused at 127.0.0.1:11434")

    monkeypatch.setattr(api, "ask_with_graph", boom)

    response = client.post("/chat", headers=headers, json={"question": "Q?"})

    assert response.status_code == 500
    assert "ollama" not in response.text.lower()
