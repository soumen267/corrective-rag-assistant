"""Corrective-RAG workflow routing, with every model call mocked."""

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

import rag_graph
from conversation import ConversationHistory


def make_result(chunk_id="c1", text="Laravel middleware filters requests."):
    document = Document(
        page_content=text,
        metadata={
            "chunk_id": chunk_id,
            "source": "data/laravel/middleware.md",
            "file_name": "middleware.md",
            "file_type": "md",
        },
    )
    return (document, 0.87)


class FakeLLM:
    def __init__(self, reply="Middleware filters HTTP requests [Source 1]."):
        self.reply = reply
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content=self.reply)


@pytest.fixture()
def pipeline(monkeypatch):
    """Patch every external dependency and record how the graph used them."""
    state = SimpleNamespace(
        retrieval_queries=[],
        grade_queries=[],
        llm=FakeLLM(),
        corrective_calls=0,
        retrieve_results=[[make_result()]],  # one entry per retrieval attempt
        grade_results=[[make_result()]],  # one entry per grading attempt
    )

    monkeypatch.setattr(
        rag_graph, "rewrite_query", lambda question, history: f"rewritten: {question}"
    )

    def fake_retrieve(query, owner_id):
        assert owner_id == "alice"
        state.retrieval_queries.append(query)
        index = min(len(state.retrieval_queries) - 1, len(state.retrieve_results) - 1)
        return state.retrieve_results[index]

    def fake_grade(question, search_results):
        state.grade_queries.append(question)
        index = min(len(state.grade_queries) - 1, len(state.grade_results) - 1)
        return state.grade_results[index]

    def fake_corrective(question, previous_query):
        state.corrective_calls += 1
        return f"corrected {state.corrective_calls}: {question}"

    monkeypatch.setattr(rag_graph, "retrieve_documents", fake_retrieve)
    monkeypatch.setattr(rag_graph, "grade_documents", fake_grade)
    monkeypatch.setattr(rag_graph, "rewrite_for_retrieval", fake_corrective)
    monkeypatch.setattr(rag_graph, "get_llm", lambda: state.llm)

    return state


def ask(question="How does middleware work?"):
    history = ConversationHistory()
    answer, citations = rag_graph.ask_with_graph(question, history, owner_id="alice")
    return answer, citations, history


# --- routing function -------------------------------------------------------


@pytest.mark.parametrize(
    ("documents", "retries", "expected"),
    [
        ([object()], 0, "generate"),
        ([object()], 1, "generate"),  # relevant docs win even on the last retry
        ([], 0, "rewrite"),
        ([], 1, "fallback"),
    ],
)
def test_route_after_grading(documents, retries, expected):
    state = {"documents": documents, "retry_count": retries, "max_retries": 1}

    assert rag_graph.route_after_grading(state) == expected


# --- end to end -------------------------------------------------------------


def test_happy_path_generates_with_citations(pipeline):
    answer, citations, _ = ask()

    assert answer == "Middleware filters HTTP requests [Source 1]."
    assert len(citations) == 1
    assert citations[0].chunk_id == "c1"
    assert pipeline.corrective_calls == 0
    assert len(pipeline.llm.calls) == 1


def test_retrieval_uses_the_rewritten_query(pipeline):
    ask("and how is it registered?")

    assert pipeline.retrieval_queries == ["rewritten: and how is it registered?"]


def test_irrelevant_first_attempt_triggers_one_corrective_retry(pipeline):
    pipeline.retrieve_results = [[make_result("bad")], [make_result("good")]]
    pipeline.grade_results = [[], [make_result("good")]]

    answer, citations, _ = ask()

    assert pipeline.corrective_calls == 1
    assert len(pipeline.retrieval_queries) == 2
    assert pipeline.retrieval_queries[1].startswith("corrected 1")
    assert citations[0].chunk_id == "good"
    assert answer.startswith("Middleware")


def test_gives_up_after_max_retries_without_calling_the_generator(pipeline):
    pipeline.grade_results = [[]]  # nothing is ever relevant

    answer, citations, _ = ask("Who won the football match yesterday?")

    assert answer == "I don't have enough information in the provided documents."
    assert citations == []
    assert pipeline.corrective_calls == 1  # max_retries = 1
    assert len(pipeline.retrieval_queries) == 2
    assert pipeline.llm.calls == []  # no hallucination opportunity


def test_empty_retrieval_skips_grading_and_falls_back(pipeline):
    pipeline.retrieve_results = [[]]

    answer, citations, _ = ask()

    assert pipeline.grade_queries == []  # nothing to grade, no LLM spend
    assert citations == []
    assert "don't have enough information" in answer


def test_generator_receives_context_and_history(pipeline):
    history = ConversationHistory()
    history.add_user_message("What is middleware?")
    history.add_assistant_message("A request filter.")

    rag_graph.ask_with_graph("How is it registered?", history, owner_id="alice")

    system_message, user_message = pipeline.llm.calls[0]
    assert "ONLY the retrieved context" in system_message.content
    assert "Laravel middleware filters requests." in user_message.content
    assert "[Source 1]" in user_message.content
    assert "A request filter." in user_message.content
    assert "How is it registered?" in user_message.content


def test_exchange_is_appended_to_history(pipeline):
    _, _, history = ask("How does middleware work?")

    assert [m.role for m in history.get_messages()] == ["user", "assistant"]
    assert history.get_messages()[0].content == "How does middleware work?"


def test_citations_come_only_from_graded_relevant_chunks(pipeline):
    pipeline.retrieve_results = [[make_result("keep"), make_result("drop")]]
    pipeline.grade_results = [[make_result("keep")]]

    _, citations, _ = ask()

    assert [c.chunk_id for c in citations] == ["keep"]
