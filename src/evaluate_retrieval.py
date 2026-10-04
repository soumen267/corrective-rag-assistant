import json
from pathlib import Path

from hybrid_search import hybrid_search
from reranker import rerank_documents


EVALUATION_FILE = Path("eval/retrieval_questions.json")
CANDIDATE_LIMIT = 10
FINAL_LIMIT = 3


def normalize_source(source: str) -> str:
    """
    Normalize Windows/Unix path separators so evaluation
    behaves consistently across platforms.
    """
    return source.replace("\\", "/")


def retrieve(question: str):
    """
    Run the complete retrieval pipeline without calling Ollama.
    """
    hybrid_results = hybrid_search(
        query=question,
        limit=CANDIDATE_LIMIT,
    )

    candidate_documents = [
        document
        for document, _score in hybrid_results
    ]

    return rerank_documents(
        query=question,
        documents=candidate_documents,
        limit=FINAL_LIMIT,
    )


def find_expected_rank(
    retrieved_sources: list[str],
    expected_sources: list[str],
) -> int | None:
    """
    Return the rank of the first expected source.
    """
    normalized_expected = {
        normalize_source(source)
        for source in expected_sources
    }

    for rank, source in enumerate(
        retrieved_sources,
        start=1,
    ):
        if normalize_source(source) in normalized_expected:
            return rank

    return None


def evaluate() -> None:
    if not EVALUATION_FILE.exists():
        raise FileNotFoundError(
            f"Evaluation file not found: {EVALUATION_FILE}"
        )

    with EVALUATION_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        test_cases = json.load(file)

    total_questions = len(test_cases)

    if total_questions == 0:
        print("No evaluation questions found.")
        return

    hits = 0
    reciprocal_rank_total = 0.0

    print("=" * 70)
    print("RAG Retrieval Evaluation")
    print("=" * 70)

    for index, test_case in enumerate(
        test_cases,
        start=1,
    ):
        question = test_case["question"]
        expected_sources = test_case["expected_sources"]

        results = retrieve(question)

        retrieved_sources = [
            str(document.metadata.get("source", "Unknown"))
            for document, _score in results
        ]

        rank = find_expected_rank(
            retrieved_sources,
            expected_sources,
        )

        if rank is not None:
            hits += 1
            reciprocal_rank = 1.0 / rank
            reciprocal_rank_total += reciprocal_rank

            status = "PASS"
        else:
            reciprocal_rank = 0.0
            status = "FAIL"

        print(f"\n[{index}] {status}")
        print(f"Question: {question}")
        print(
            "Expected: "
            + ", ".join(expected_sources)
        )

        print("Retrieved:")

        if not retrieved_sources:
            print("  No documents")
        else:
            for retrieved_rank, source in enumerate(
                retrieved_sources,
                start=1,
            ):
                print(
                    f"  {retrieved_rank}. "
                    f"{normalize_source(source)}"
                )

        print(
            "Expected rank: "
            f"{rank if rank is not None else 'Not found'}"
        )

        print(
            f"Reciprocal rank: "
            f"{reciprocal_rank:.3f}"
        )

    hit_rate = hits / total_questions
    mrr = reciprocal_rank_total / total_questions

    print("\n" + "=" * 70)
    print("Evaluation Summary")
    print("=" * 70)

    print(f"Questions: {total_questions}")
    print(f"Hits@{FINAL_LIMIT}: {hits}")
    print(
        f"Hit Rate@{FINAL_LIMIT}: "
        f"{hit_rate:.2%}"
    )
    print(f"MRR: {mrr:.3f}")


if __name__ == "__main__":
    evaluate()