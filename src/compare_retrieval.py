import json
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document

from hybrid_search import hybrid_search
from reranker import rerank_documents
from search import search_documents


EVALUATION_FILE = Path("eval/retrieval_questions.json")

FINAL_LIMIT = 3
CANDIDATE_LIMIT = 10

SearchResult = list[tuple[Document, float]]


def normalize_source(source: str) -> str:
    return source.replace("\\", "/")


def vector_retrieval(question: str) -> SearchResult:
    """
    Strategy A:
    Vector search only.
    """
    return search_documents(
        query=question,
        limit=FINAL_LIMIT,
    )


def hybrid_retrieval(question: str) -> SearchResult:
    """
    Strategy B:
    Vector + BM25 + RRF.
    """
    return hybrid_search(
        query=question,
        limit=FINAL_LIMIT,
    )


def reranked_retrieval(question: str) -> SearchResult:
    """
    Strategy C:
    Vector + BM25 + RRF followed by cross-encoder reranking.
    """
    hybrid_results = hybrid_search(
        query=question,
        limit=CANDIDATE_LIMIT,
    )

    candidates = [
        document
        for document, _score in hybrid_results
    ]

    return rerank_documents(
        query=question,
        documents=candidates,
        limit=FINAL_LIMIT,
    )


def get_retrieved_sources(
    results: SearchResult,
) -> list[str]:
    return [
        normalize_source(
            str(document.metadata.get("source", "Unknown"))
        )
        for document, _score in results
    ]


def find_expected_rank(
    retrieved_sources: list[str],
    expected_sources: list[str],
) -> int | None:
    expected = {
        normalize_source(source)
        for source in expected_sources
    }

    for rank, source in enumerate(
        retrieved_sources,
        start=1,
    ):
        if source in expected:
            return rank

    return None


def evaluate_strategy(
    name: str,
    retrieval_function: Callable[[str], SearchResult],
    test_cases: list[dict],
) -> dict:
    """
    Evaluate one retrieval strategy.

    Positive queries:
        Measure Hit@K and reciprocal rank.

    Rejection queries:
        expected_sources == []
        Pass only when no documents are retrieved.
    """
    positive_count = 0
    positive_hits = 0
    reciprocal_rank_total = 0.0

    rejection_count = 0
    rejection_hits = 0

    failures = []

    for test_case in test_cases:
        question = test_case["question"]
        expected_sources = test_case["expected_sources"]

        results = retrieval_function(question)

        retrieved_sources = get_retrieved_sources(results)

        # Out-of-domain / rejection test
        if not expected_sources:
            rejection_count += 1

            if not retrieved_sources:
                rejection_hits += 1
            else:
                failures.append(
                    {
                        "question": question,
                        "type": "rejection",
                        "expected": [],
                        "retrieved": retrieved_sources,
                    }
                )

            continue

        # Normal retrieval test
        positive_count += 1

        rank = find_expected_rank(
            retrieved_sources,
            expected_sources,
        )

        if rank is not None:
            positive_hits += 1
            reciprocal_rank_total += 1.0 / rank
        else:
            failures.append(
                {
                    "question": question,
                    "type": "retrieval",
                    "expected": expected_sources,
                    "retrieved": retrieved_sources,
                }
            )

    hit_rate = (
        positive_hits / positive_count
        if positive_count
        else 0.0
    )

    mrr = (
        reciprocal_rank_total / positive_count
        if positive_count
        else 0.0
    )

    rejection_accuracy = (
        rejection_hits / rejection_count
        if rejection_count
        else None
    )

    return {
        "name": name,
        "positive_count": positive_count,
        "hits": positive_hits,
        "hit_rate": hit_rate,
        "mrr": mrr,
        "rejection_count": rejection_count,
        "rejection_hits": rejection_hits,
        "rejection_accuracy": rejection_accuracy,
        "failures": failures,
    }


def print_results(results: list[dict]) -> None:
    print("\n" + "=" * 80)
    print("Retrieval Strategy Comparison")
    print("=" * 80)

    print(
        f"{'Strategy':<25}"
        f"{'Hit@3':>12}"
        f"{'MRR':>12}"
        f"{'Rejection':>15}"
    )

    print("-" * 80)

    for result in results:
        rejection_accuracy = result["rejection_accuracy"]

        if rejection_accuracy is None:
            rejection_text = "N/A"
        else:
            rejection_text = (
                f"{rejection_accuracy:.2%}"
            )

        print(
            f"{result['name']:<25}"
            f"{result['hit_rate']:>11.2%}"
            f"{result['mrr']:>12.3f}"
            f"{rejection_text:>15}"
        )

    print("=" * 80)


def print_failures(results: list[dict]) -> None:
    has_failures = False

    for result in results:
        if not result["failures"]:
            continue

        has_failures = True

        print(f"\nFailures: {result['name']}")
        print("-" * 60)

        for failure in result["failures"]:
            print(f"\nQuestion: {failure['question']}")

            if failure["type"] == "rejection":
                print("Expected: no documents")
            else:
                print(
                    "Expected: "
                    + ", ".join(failure["expected"])
                )

            print("Retrieved:")

            if not failure["retrieved"]:
                print("  No documents")
            else:
                for index, source in enumerate(
                    failure["retrieved"],
                    start=1,
                ):
                    print(f"  {index}. {source}")

    if not has_failures:
        print("\nNo failures found.")


def main() -> None:
    if not EVALUATION_FILE.exists():
        raise FileNotFoundError(
            f"Evaluation file not found: {EVALUATION_FILE}"
        )

    with EVALUATION_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        test_cases = json.load(file)

    strategies = [
        (
            "Vector Only",
            vector_retrieval,
        ),
        (
            "Hybrid",
            hybrid_retrieval,
        ),
        (
            "Hybrid + Reranker",
            reranked_retrieval,
        ),
    ]

    results = []

    for name, retrieval_function in strategies:
        print(f"\nEvaluating: {name}")

        result = evaluate_strategy(
            name=name,
            retrieval_function=retrieval_function,
            test_cases=test_cases,
        )

        results.append(result)

    print_results(results)
    print_failures(results)


if __name__ == "__main__":
    main()