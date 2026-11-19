"""Question-by-question view of the production retrieval pipeline.

Run from the project root:

    python src/evaluate_retrieval.py

Uses the same isolated evaluation corpus as compare_retrieval.py, so it never
touches your real documents or vector store.
"""

import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_retrieval import find_expected_rank, reranked_retrieval  # noqa: E402
from eval_env import isolated_eval_index, load_questions, source_name  # noqa: E402
from rag import FINAL_LIMIT  # noqa: E402


def evaluate() -> None:
    test_cases = load_questions()

    # Skip out-of-scope questions: they are measured by compare_retrieval.py
    # through the reranker score analysis.
    in_scope = [case for case in test_cases if case["expected_sources"]]

    hits = 0
    reciprocal_rank_total = 0.0

    with contextlib.redirect_stdout(sys.stderr):
        index = isolated_eval_index()
        owner_id = index.__enter__()

    try:
        print("=" * 70)
        print("RAG Retrieval Evaluation (hybrid + cross-encoder reranker)")
        print("=" * 70)

        for number, case in enumerate(in_scope, start=1):
            with contextlib.redirect_stdout(sys.stderr):
                results = reranked_retrieval(case["question"], owner_id)

            retrieved = [str(d.metadata.get("source", "")) for d, _s in results]
            rank = find_expected_rank(retrieved, case["expected_sources"])

            if rank is not None:
                hits += 1
                reciprocal_rank_total += 1.0 / rank

            print(f"\n[{number}] {'PASS' if rank is not None else 'FAIL'} "
                  f"[{case.get('type', 'other')}]")
            print(f"Question: {case['question']}")
            print("Expected: " + ", ".join(case["expected_sources"]))
            print("Retrieved:")

            for position, (document, score) in enumerate(results, start=1):
                print(f"  {position}. {source_name(str(document.metadata.get('source')))}"
                      f"  (reranker score {score:.2f})")

            if not results:
                print("  No documents")

            print(f"Expected rank: {rank if rank is not None else 'Not found'}")
    finally:
        index.__exit__(None, None, None)

    total = len(in_scope)
    print("\n" + "=" * 70)
    print("Evaluation Summary")
    print("=" * 70)
    print(f"In-scope questions: {total}")
    print(f"Hits@{FINAL_LIMIT}: {hits}")
    print(f"Hit Rate@{FINAL_LIMIT}: {hits / total:.2%}")
    print(f"MRR: {reciprocal_rank_total / total:.3f}")


if __name__ == "__main__":
    evaluate()
