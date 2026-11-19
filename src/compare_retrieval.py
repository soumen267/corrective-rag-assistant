"""Compare retrieval strategies on the bundled, isolated evaluation corpus.

Run from the project root:

    python src/compare_retrieval.py            # human-readable report
    python src/compare_retrieval.py --markdown # README-ready tables

The corpus in eval/corpus is indexed into a temporary store, so the run is
reproducible and never touches your real documents, vectors or database.
"""

import argparse
import contextlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_env import isolated_eval_index, load_questions, source_name  # noqa: E402
from hybrid_search import hybrid_search  # noqa: E402
from rag import CANDIDATE_LIMIT, FINAL_LIMIT  # noqa: E402
from reranker import rerank_documents  # noqa: E402
from search import search_documents  # noqa: E402

SearchResult = list[tuple[Document, float]]
RetrievalFunction = Callable[[str, str], SearchResult]


# ---------------------------------------------------------------------------
# Strategies (FINAL_LIMIT / CANDIDATE_LIMIT match the production pipeline)
# ---------------------------------------------------------------------------


def vector_retrieval(question: str, owner_id: str) -> SearchResult:
    """Strategy A: vector search only."""
    return search_documents(
        query=question,
        limit=FINAL_LIMIT,
        owner_id=owner_id,
    )


def vector_retrieval_no_cutoff(question: str, owner_id: str) -> SearchResult:
    """Strategy A2: vector search ranking only, without the distance cutoff.

    Separates ranking quality from the effect of the production
    MAX_DISTANCE threshold, which discards weak matches.
    """
    return search_documents(
        query=question,
        limit=FINAL_LIMIT,
        max_distance=float("inf"),
        owner_id=owner_id,
    )


def hybrid_retrieval(question: str, owner_id: str) -> SearchResult:
    """Strategy B: vector + BM25 fused with Reciprocal Rank Fusion."""
    return hybrid_search(
        query=question,
        limit=FINAL_LIMIT,
        owner_id=owner_id,
    )


def reranked_retrieval(question: str, owner_id: str) -> SearchResult:
    """Strategy C: hybrid candidates reranked by the cross-encoder."""
    candidates = [
        document
        for document, _score in hybrid_search(
            query=question,
            limit=CANDIDATE_LIMIT,
            owner_id=owner_id,
        )
    ]

    return rerank_documents(
        query=question,
        documents=candidates,
        limit=FINAL_LIMIT,
    )


STRATEGIES: list[tuple[str, RetrievalFunction]] = [
    ("Vector only (distance cutoff)", vector_retrieval),
    ("Vector only (no cutoff)", vector_retrieval_no_cutoff),
    ("Hybrid (vector + BM25 + RRF)", hybrid_retrieval),
    ("Hybrid + cross-encoder rerank", reranked_retrieval),
]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def find_expected_rank(
    retrieved_sources: list[str],
    expected_sources: list[str],
) -> int | None:
    """1-based rank of the first expected file, or None if absent."""
    expected = {source_name(source) for source in expected_sources}

    for rank, source in enumerate(retrieved_sources, start=1):
        if source_name(source) in expected:
            return rank

    return None


def evaluate_strategy(
    name: str,
    retrieval_function: RetrievalFunction,
    test_cases: list[dict],
    owner_id: str,
) -> dict:
    """Score one strategy.

    In-scope questions: Hit@1, Hit@3 and reciprocal rank.
    Out-of-scope questions (expected_sources == []): counted as correct only
    when the retriever returns nothing. Strategies without a score threshold
    always return something, so this column is informative mainly for vector
    search; see `threshold_analysis` for the reranker.
    """
    totals = defaultdict(lambda: {"count": 0, "hit1": 0, "hit3": 0, "rr": 0.0})
    overall = {"count": 0, "hit1": 0, "hit3": 0, "rr": 0.0}
    rejection = {"count": 0, "correct": 0}
    failures: list[dict] = []
    in_scope_top_scores: list[float] = []
    out_of_scope_top_scores: list[float] = []

    for case in test_cases:
        question = case["question"]
        expected = case["expected_sources"]
        results = retrieval_function(question, owner_id)
        retrieved = [str(d.metadata.get("source", "")) for d, _s in results]
        top_score = results[0][1] if results else None

        if not expected:
            rejection["count"] += 1
            if top_score is not None:
                out_of_scope_top_scores.append(top_score)
            if not retrieved:
                rejection["correct"] += 1
            else:
                failures.append(
                    {"question": question, "type": "rejection", "expected": [],
                     "retrieved": [source_name(s) for s in retrieved]}
                )
            continue

        if top_score is not None:
            in_scope_top_scores.append(top_score)

        rank = find_expected_rank(retrieved, expected)
        bucket = totals[case.get("type", "other")]

        for target in (bucket, overall):
            target["count"] += 1
            if rank == 1:
                target["hit1"] += 1
            if rank is not None:
                target["hit3"] += 1
                target["rr"] += 1.0 / rank

        if rank is None:
            failures.append(
                {"question": question, "type": case.get("type", "other"),
                 "expected": expected,
                 "retrieved": [source_name(s) for s in retrieved]}
            )

    return {
        "name": name,
        "overall": overall,
        "by_type": dict(totals),
        "rejection": rejection,
        "failures": failures,
        "in_scope_top_scores": in_scope_top_scores,
        "out_of_scope_top_scores": out_of_scope_top_scores,
    }


def rate(numerator: float, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def threshold_analysis(positive: list[float], negative: list[float]) -> dict | None:
    """How well does the top-1 score separate in-scope from out-of-scope?

    Returns the ROC AUC (probability that a random in-scope question scores
    higher than a random out-of-scope one) and the threshold with the best
    overall accuracy.
    """
    if not positive or not negative:
        return None

    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0
        for p in positive
        for n in negative
    )
    auc = wins / (len(positive) * len(negative))

    best = None
    for threshold in sorted(set(positive + negative)):
        kept = sum(score >= threshold for score in positive)
        rejected = sum(score < threshold for score in negative)
        accuracy = (kept + rejected) / (len(positive) + len(negative))

        if best is None or accuracy > best["accuracy"]:
            best = {
                "threshold": threshold,
                "accuracy": accuracy,
                "in_scope_kept": kept / len(positive),
                "out_of_scope_rejected": rejected / len(negative),
            }

    return {
        "auc": auc,
        "lowest_in_scope": min(positive),
        "highest_out_of_scope": max(negative),
        **best,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

TYPE_LABELS = {
    "paraphrase": "Paraphrased questions",
    "keyword": "Keyword / identifier queries",
    "multi_doc": "Multi-document questions",
}


def print_text_report(results: list[dict], analysis: dict | None) -> None:
    print("\n" + "=" * 86)
    print(f"Retrieval strategy comparison (top-{FINAL_LIMIT} results)")
    print("=" * 86)
    print(f"{'Strategy':<34}{'Hit@1':>9}{'Hit@3':>9}{'MRR':>9}{'Reject':>12}")
    print("-" * 86)

    for result in results:
        o, r = result["overall"], result["rejection"]
        print(
            f"{result['name']:<34}"
            f"{rate(o['hit1'], o['count']):>9.1%}"
            f"{rate(o['hit3'], o['count']):>9.1%}"
            f"{rate(o['rr'], o['count']):>9.3f}"
            f"{rate(r['correct'], r['count']):>12.0%}"
        )

    print("=" * 86)
    print(f"In-scope questions: {results[0]['overall']['count']}   "
          f"Out-of-scope: {results[0]['rejection']['count']}")

    print("\nHit@3 by question type")
    print("-" * 86)
    for type_key, label in TYPE_LABELS.items():
        row = f"{label:<34}"
        for result in results:
            bucket = result["by_type"].get(type_key)
            row += f"{rate(bucket['hit3'], bucket['count']) if bucket else 0:>9.0%}"
        print(row)
    print("(columns follow the strategy order above)")

    if analysis:
        print("\nOut-of-scope detection with the reranker's top-1 score")
        print("-" * 86)
        print(f"ROC AUC: {analysis['auc']:.3f}")
        print(
            f"Lowest in-scope top-1 score: {analysis['lowest_in_scope']:.2f}   "
            f"Highest out-of-scope top-1 score: {analysis['highest_out_of_scope']:.2f}"
        )
        print(
            f"Best threshold {analysis['threshold']:.2f}: keeps "
            f"{analysis['in_scope_kept']:.0%} of in-scope and rejects "
            f"{analysis['out_of_scope_rejected']:.0%} of out-of-scope questions"
        )

    for result in results:
        if not result["failures"]:
            continue
        print(f"\nFailures: {result['name']}")
        print("-" * 86)
        for failure in result["failures"]:
            expected = ", ".join(failure["expected"]) or "(nothing)"
            print(f"  [{failure['type']}] {failure['question']}")
            print(f"      expected: {expected}")
            print(f"      got:      {', '.join(failure['retrieved']) or '(nothing)'}")


def print_markdown_report(results: list[dict], analysis: dict | None) -> None:
    o = results[0]["overall"]
    print(f"| Strategy | Hit@1 | Hit@{FINAL_LIMIT} | MRR |")
    print("|---|---|---|---|")
    for result in results:
        ov = result["overall"]
        print(
            f"| {result['name']} | {rate(ov['hit1'], ov['count']):.1%} | "
            f"{rate(ov['hit3'], ov['count']):.1%} | "
            f"{rate(ov['rr'], ov['count']):.3f} |"
        )

    print(f"\n*{o['count']} in-scope questions, "
          f"{results[0]['rejection']['count']} out-of-scope.*\n")

    print(f"| Hit@{FINAL_LIMIT} by question type | "
          + " | ".join(r["name"] for r in results) + " |")
    print("|---|" + "---|" * len(results))
    for type_key, label in TYPE_LABELS.items():
        cells = []
        for result in results:
            bucket = result["by_type"].get(type_key)
            cells.append(f"{rate(bucket['hit3'], bucket['count']):.0%}" if bucket else "-")
        count = results[0]["by_type"].get(type_key, {}).get("count", 0)
        print(f"| {label} ({count}) | " + " | ".join(cells) + " |")

    if analysis:
        print(
            f"\nReranker top-1 score separates in-scope from out-of-scope "
            f"questions with ROC AUC **{analysis['auc']:.3f}**. The lowest "
            f"in-scope top-1 score is {analysis['lowest_in_scope']:.2f} and the "
            f"highest out-of-scope score is {analysis['highest_out_of_scope']:.2f}; "
            f"the best threshold ({analysis['threshold']:.2f}) keeps "
            f"{analysis['in_scope_kept']:.0%} of in-scope questions and "
            f"rejects {analysis['out_of_scope_rejected']:.0%} of out-of-scope ones."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--markdown", action="store_true",
                        help="print README-ready tables instead of the text report")
    args = parser.parse_args()

    test_cases = load_questions()

    # Loader progress messages go to stderr so stdout contains only the report.
    with contextlib.redirect_stdout(sys.stderr):
        with isolated_eval_index() as owner_id:
            results = []
            for name, retrieval_function in STRATEGIES:
                print(f"Evaluating: {name}")
                results.append(
                    evaluate_strategy(name, retrieval_function, test_cases, owner_id)
                )

    reranked = results[-1]
    analysis = threshold_analysis(
        reranked["in_scope_top_scores"],
        reranked["out_of_scope_top_scores"],
    )

    if args.markdown:
        print_markdown_report(results, analysis)
    else:
        print_text_report(results, analysis)


if __name__ == "__main__":
    main()
