"""Evaluation dataset integrity and metric helpers (no models required)."""

from collections import Counter

import pytest

import compare_retrieval as cr
from eval_env import CORPUS_DIRECTORY, load_questions, source_name

VALID_TYPES = {"paraphrase", "keyword", "multi_doc", "out_of_scope"}


@pytest.fixture(scope="module")
def questions():
    return load_questions()


@pytest.fixture(scope="module")
def corpus_files():
    return {path.name for path in CORPUS_DIRECTORY.glob("*.md")}


def test_dataset_is_large_enough_to_mean_something(questions):
    in_scope = [q for q in questions if q["expected_sources"]]
    out_of_scope = [q for q in questions if not q["expected_sources"]]

    assert len(in_scope) >= 40
    assert len(out_of_scope) >= 10


def test_every_question_is_well_formed(questions):
    for question in questions:
        assert question["type"] in VALID_TYPES
        assert question["question"].strip()
        assert isinstance(question["expected_sources"], list)


def test_questions_are_unique(questions):
    texts = [q["question"].strip().lower() for q in questions]

    assert [t for t, n in Counter(texts).items() if n > 1] == []


def test_out_of_scope_type_matches_empty_expectation(questions):
    for question in questions:
        assert (question["type"] == "out_of_scope") == (not question["expected_sources"])


def test_expected_sources_exist_in_the_corpus(questions, corpus_files):
    expected = {name for q in questions for name in q["expected_sources"]}

    assert expected - corpus_files == set()


def test_every_corpus_document_is_covered_by_a_question(questions, corpus_files):
    expected = {name for q in questions for name in q["expected_sources"]}

    assert corpus_files - expected == set()


def test_corpus_documents_span_multiple_chunks(corpus_files):
    # Documents shorter than one chunk (500 characters) make retrieval trivial.
    for name in corpus_files:
        assert len((CORPUS_DIRECTORY / name).read_text(encoding="utf-8")) > 1200, name


# --- metric helpers ---------------------------------------------------------


def test_source_name_handles_both_separators():
    assert source_name("C:\\data\\users\\abc\\notes.md") == "notes.md"
    assert source_name("data/users/abc/notes.md") == "notes.md"


def test_find_expected_rank():
    retrieved = ["/x/a.md", "/x/b.md", "/x/c.md"]

    assert cr.find_expected_rank(retrieved, ["b.md"]) == 2
    assert cr.find_expected_rank(retrieved, ["z.md", "c.md"]) == 3
    assert cr.find_expected_rank(retrieved, ["z.md"]) is None
    assert cr.find_expected_rank([], ["a.md"]) is None


def test_threshold_analysis_perfect_separation():
    analysis = cr.threshold_analysis([5.0, 4.0, 3.0], [-1.0, -2.0])

    assert analysis["auc"] == 1.0
    assert analysis["in_scope_kept"] == 1.0
    assert analysis["out_of_scope_rejected"] == 1.0
    assert analysis["lowest_in_scope"] == 3.0
    assert analysis["highest_out_of_scope"] == -1.0


def test_threshold_analysis_with_overlap():
    analysis = cr.threshold_analysis([1.0, 3.0], [2.0])

    assert analysis["auc"] == pytest.approx(0.5)


def test_threshold_analysis_needs_both_classes():
    assert cr.threshold_analysis([], [1.0]) is None
    assert cr.threshold_analysis([1.0], []) is None
