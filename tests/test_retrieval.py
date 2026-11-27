"""Hybrid retrieval: Reciprocal Rank Fusion and owner isolation."""

import pytest
from langchain_core.documents import Document

import hybrid_search
import knowledge_base
from bm25_search import BM25Search, clear_bm25_cache, tokenize


def doc(chunk_id: str, text: str = "") -> Document:
    return Document(
        page_content=text or f"content of {chunk_id}",
        metadata={"chunk_id": chunk_id},
    )


def patch_sources(monkeypatch, vector, bm25):
    monkeypatch.setattr(
        hybrid_search,
        "search_documents",
        lambda query, limit, owner_id: [(d, 0.0) for d in vector],
    )

    class FakeBM25:
        def __init__(self, owner_id):
            pass

        def search(self, query, limit):
            return [(d, 0.0) for d in bm25]

    monkeypatch.setattr(hybrid_search, "BM25Search", FakeBM25)


def test_reciprocal_rank_formula():
    assert hybrid_search.reciprocal_rank(1) == pytest.approx(1 / 61)
    assert hybrid_search.reciprocal_rank(10) == pytest.approx(1 / 70)


def test_document_found_by_both_retrievers_ranks_first(monkeypatch):
    shared, vector_only, bm25_only = doc("shared"), doc("v"), doc("b")
    # `shared` is only 2nd in each list, yet beats the single-list winners.
    patch_sources(
        monkeypatch,
        vector=[vector_only, shared],
        bm25=[bm25_only, shared],
    )

    results = hybrid_search.hybrid_search("query", owner_id="alice")
    ids = [d.metadata["chunk_id"] for d, _ in results]

    assert ids[0] == "shared"
    assert set(ids) == {"shared", "v", "b"}


def test_fused_score_is_sum_of_reciprocal_ranks(monkeypatch):
    shared = doc("shared")
    patch_sources(monkeypatch, vector=[shared], bm25=[doc("x"), shared])

    results = dict(
        (d.metadata["chunk_id"], s)
        for d, s in hybrid_search.hybrid_search("query", owner_id="alice")
    )

    expected = hybrid_search.reciprocal_rank(1) + hybrid_search.reciprocal_rank(2)
    assert results["shared"] == pytest.approx(expected)


def test_duplicates_are_returned_once(monkeypatch):
    shared = doc("shared")
    patch_sources(monkeypatch, vector=[shared], bm25=[shared])

    results = hybrid_search.hybrid_search("query", owner_id="alice")

    assert len(results) == 1


def test_limit_is_respected(monkeypatch):
    patch_sources(
        monkeypatch,
        vector=[doc(f"v{i}") for i in range(5)],
        bm25=[doc(f"b{i}") for i in range(5)],
    )

    assert len(hybrid_search.hybrid_search("q", limit=3, owner_id="alice")) == 3


def test_blank_query_returns_nothing(monkeypatch):
    patch_sources(monkeypatch, vector=[doc("v")], bm25=[doc("b")])

    assert hybrid_search.hybrid_search("   ", owner_id="alice") == []


def test_owner_id_is_mandatory(monkeypatch):
    patch_sources(monkeypatch, vector=[], bm25=[])

    with pytest.raises(ValueError):
        hybrid_search.hybrid_search("query")


def test_empty_results_from_both_sources(monkeypatch):
    patch_sources(monkeypatch, vector=[], bm25=[])

    assert hybrid_search.hybrid_search("query", owner_id="alice") == []


# --- BM25 -------------------------------------------------------------------


def test_tokenizer_lowercases_and_drops_stop_words():
    assert tokenize("What IS the Laravel Middleware?") == ["laravel", "middleware"]


def test_bm25_only_searches_the_owners_files(monkeypatch, tmp_path):
    monkeypatch.setattr(knowledge_base, "DATA_DIRECTORY", tmp_path / "data")
    clear_bm25_cache()

    for owner, text in (
        ("alice", "Alice documents describe quantum widgets in detail."),
        ("bob", "Bob documents describe espresso machines in detail."),
    ):
        directory = knowledge_base.get_user_data_directory(owner)
        directory.mkdir(parents=True)
        (directory / "notes.txt").write_text(text, encoding="utf-8")

    alice = BM25Search("alice").search("quantum widgets")
    cross_tenant = BM25Search("bob").search("quantum widgets")

    assert alice
    assert "quantum" in alice[0][0].page_content
    assert cross_tenant == []  # Bob must never see Alice's content


def test_bm25_index_refreshes_after_a_file_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(knowledge_base, "DATA_DIRECTORY", tmp_path / "data")
    clear_bm25_cache()

    directory = knowledge_base.get_user_data_directory("alice")
    directory.mkdir(parents=True)
    (directory / "notes.txt").write_text("alpha beta gamma", encoding="utf-8")

    assert BM25Search("alice").search("zebra") == []

    (directory / "later.txt").write_text("zebra crossing ahead", encoding="utf-8")

    assert BM25Search("alice").search("zebra")


def test_bm25_requires_a_valid_owner():
    with pytest.raises(ValueError):
        BM25Search("   ")
