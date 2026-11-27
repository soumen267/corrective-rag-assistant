"""Upload validation, deletion and per-user isolation."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import select

import api
import document_models
import knowledge_base
import vector_store


# --- validate_upload_content ------------------------------------------------


def test_valid_pdf_header_accepted(tmp_path):
    path = tmp_path / "ok.pdf"
    path.write_bytes(b"%PDF-1.7\n...")

    api.validate_upload_content(path, ".pdf")


def test_fake_pdf_rejected(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"<html>not a pdf</html>")

    with pytest.raises(HTTPException) as error:
        api.validate_upload_content(path, ".pdf")

    assert error.value.status_code == 400


def test_binary_content_rejected_for_text_files(tmp_path):
    path = tmp_path / "bin.txt"
    path.write_bytes(b"hello\x00world")

    with pytest.raises(HTTPException):
        api.validate_upload_content(path, ".txt")


def test_non_utf8_rejected_for_text_files(tmp_path):
    path = tmp_path / "latin.md"
    path.write_bytes("caf\xe9".encode("latin-1"))

    with pytest.raises(HTTPException):
        api.validate_upload_content(path, ".md")


def test_utf8_text_accepted(tmp_path):
    path = tmp_path / "ok.md"
    path.write_text("# Title\nCafé ☕", encoding="utf-8")

    api.validate_upload_content(path, ".md")


# --- /documents endpoint ----------------------------------------------------


def test_unsupported_extension_rejected(client, auth_headers):
    headers = auth_headers("alice")

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("malware.exe", b"MZ...", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


def test_oversized_upload_rejected_and_not_left_on_disk(
    client, auth_headers, monkeypatch, tmp_path
):
    headers = auth_headers("alice")
    monkeypatch.setattr(api, "MAX_UPLOAD_SIZE", 100)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("big.txt", b"a" * 500, "text/plain")},
    )

    assert response.status_code == 413
    leftovers = [
        p for p in (tmp_path / "data").rglob("*") if p.is_file()
    ]
    assert leftovers == []


def test_invalid_content_rejected_and_not_left_on_disk(
    client, auth_headers, tmp_path
):
    headers = auth_headers("alice")

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("fake.pdf", b"<html>not a pdf</html>", "application/pdf")},
    )

    assert response.status_code == 400
    assert [p for p in (tmp_path / "data").rglob("*") if p.is_file()] == []


def test_path_traversal_filename_is_flattened(
    client, auth_headers, monkeypatch, tmp_path
):
    headers = auth_headers("alice")
    indexed = {}

    def fake_index_file(path, owner_id=None, display_name=None):
        indexed["path"] = path
        return 3

    monkeypatch.setattr(api, "index_file", fake_index_file)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("../../evil.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["file_name"] == "evil.txt"

    stored = indexed["path"].resolve()
    user_dir = knowledge_base.get_user_data_directory("alice").resolve()
    assert stored.parent == user_dir


def test_upload_keeps_the_original_name_for_citations_and_listing(
    client, auth_headers, monkeypatch
):
    headers = auth_headers("alice")
    seen = {}

    def fake_index_file(path, owner_id=None, display_name=None):
        seen["display_name"] = display_name
        return 2

    monkeypatch.setattr(api, "index_file", fake_index_file)
    monkeypatch.setattr(
        api, "list_knowledge_files", lambda owner_id=None: [seen["stored"]]
    )

    upload = client.post(
        "/documents",
        headers=headers,
        files={"file": ("Sanctum Guide.pdf", b"%PDF-1.4 x", "application/pdf")},
    )
    seen["stored"] = upload.json()["source"]
    listing = client.get("/documents", headers=headers)

    assert upload.status_code == 200
    assert seen["display_name"] == "Sanctum Guide.pdf"
    assert listing.json()["names"] == {seen["stored"]: "Sanctum Guide.pdf"}


def test_unchanged_reupload_is_deduplicated(client, auth_headers, monkeypatch):
    headers = auth_headers("alice")
    calls = []

    def fake_index_file(path, owner_id=None, display_name=None):
        calls.append(path)
        return 2

    monkeypatch.setattr(api, "index_file", fake_index_file)

    upload = {"file": ("notes.txt", b"same content", "text/plain")}
    first = client.post("/documents", headers=headers, files=upload)
    second = client.post(
        "/documents",
        headers=headers,
        files={"file": ("notes.txt", b"same content", "text/plain")},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["chunks_indexed"] == 0
    assert "unchanged" in second.json()["message"].lower()
    assert len(calls) == 1


def test_failed_indexing_cleans_up_the_uploaded_file(
    client, auth_headers, monkeypatch, tmp_path
):
    headers = auth_headers("alice")

    def failing_index(path, owner_id=None, display_name=None):
        raise RuntimeError("embedding model crashed")

    monkeypatch.setattr(api, "index_file", failing_index)
    monkeypatch.setattr(api, "delete_file_from_index", lambda *a, **k: None)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("notes.txt", b"content", "text/plain")},
    )

    assert response.status_code == 500
    assert "embedding" not in response.text  # internals are not leaked
    leftovers = [p for p in (tmp_path / "data").rglob("*") if p.is_file()]
    assert leftovers == []


def test_delete_refuses_files_outside_the_users_directory(
    client, auth_headers, tmp_path
):
    headers = auth_headers("alice")
    outside = tmp_path / "secret.txt"
    outside.write_text("do not delete")

    response = client.delete(
        "/documents",
        headers=headers,
        params={"source": str(outside)},
    )

    assert response.status_code == 400
    assert outside.exists()


def test_user_cannot_delete_another_users_document(
    client, auth_headers, make_user
):
    alice_headers = auth_headers("alice")
    make_user("mallory")
    mallory = client.post(
        "/auth/login",
        json={"username": "mallory", "password": "correct-horse-battery"},
    ).json()["access_token"]

    alice_dir = knowledge_base.get_user_data_directory("alice")
    alice_dir.mkdir(parents=True)
    alices_file = alice_dir / "private.txt"
    alices_file.write_text("alice only")

    response = client.delete(
        "/documents",
        headers={"Authorization": f"Bearer {mallory}"},
        params={"source": str(alices_file)},
    )

    assert response.status_code == 400
    assert alices_file.exists()
    assert alice_headers  # alice's own token is unaffected


# --- delete removes the file, the vectors and the registry row --------------


@pytest.fixture()
def real_index(client, monkeypatch, tmp_path):
    """Real Chroma with fake embeddings and a *relative* data directory.

    Production stores relative paths ("data/users/..."). An absolute test
    directory would hide any mismatch between stored and resolved paths.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(knowledge_base, "DATA_DIRECTORY", Path("data"))
    # Absolute, because Chroma caches clients by path string across tests.
    monkeypatch.setattr(vector_store, "VECTOR_STORE_PATH", tmp_path / "vector_store")
    embeddings = DeterministicFakeEmbedding(size=32)
    monkeypatch.setattr(vector_store, "get_embedding_model", lambda: embeddings)

    return lambda: vector_store.get_vector_store().get(include=["metadatas"])


def upload_notes(client, headers):
    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("notes.txt", b"The deploy code is QX-7741.", "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def registry_rows(session_factory):
    with session_factory() as db:
        return db.scalars(select(document_models.UserDocument)).all()


@pytest.mark.parametrize("path_style", ["as_listed", "absolute"])
def test_delete_removes_file_vectors_and_registry_row(
    client, auth_headers, real_index, sqlite_session_factory, path_style
):
    headers = auth_headers("alice")
    source = upload_notes(client, headers)["source"]
    assert len(real_index()["ids"]) == 1

    requested = source if path_style == "as_listed" else str(Path(source).resolve())
    response = client.delete(
        "/documents", headers=headers, params={"source": requested}
    )

    assert response.status_code == 200, response.text
    assert response.json()["source"] == source
    assert not Path(source).exists()
    assert real_index()["ids"] == []
    assert registry_rows(sqlite_session_factory) == []

    # The same content can be uploaded again and is really indexed.
    assert upload_notes(client, headers)["chunks_indexed"] == 1
    assert len(real_index()["ids"]) == 1


def test_reupload_repairs_a_record_whose_file_is_missing(
    client, auth_headers, real_index, sqlite_session_factory
):
    """Rows and vectors left behind by the old delete bug must not block uploads."""
    headers = auth_headers("alice")
    old_source = upload_notes(client, headers)["source"]
    Path(old_source).unlink()

    result = upload_notes(client, headers)

    assert result["chunks_indexed"] == 1
    assert result["source"] != old_source
    assert Path(result["source"]).is_file()
    assert [m["source"] for m in real_index()["metadatas"]] == [result["source"]]
    assert [r.stored_path for r in registry_rows(sqlite_session_factory)] == [
        result["source"]
    ]


# --- directory isolation ----------------------------------------------------


def test_each_owner_gets_a_distinct_directory():
    assert (
        knowledge_base.get_user_data_directory("alice")
        != knowledge_base.get_user_data_directory("bob")
    )


def test_hostile_owner_ids_cannot_escape_the_data_directory():
    directory = knowledge_base.get_user_data_directory("../../etc/passwd")

    assert ".." not in directory.parts
    assert directory.parent == knowledge_base.DATA_DIRECTORY / "users"


@pytest.mark.parametrize("owner", ["", "   ", None])
def test_blank_owner_is_rejected(owner):
    with pytest.raises(ValueError):
        knowledge_base.get_user_data_directory(owner)
