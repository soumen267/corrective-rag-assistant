
import logging
from functools import lru_cache

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """
    Load the cross-encoder once and reuse it.
    """
    logger.info("Loading reranker model: %s", RERANKER_MODEL)
    return CrossEncoder(RERANKER_MODEL)


def rerank_documents(
    query: str,
    documents: list[Document],
    limit: int = 3,
) -> list[tuple[Document, float]]:
    """
    Rerank candidate documents according to their
    relevance to the query.

    Returns:
        List of (Document, relevance_score) tuples.
    """

    if not query or not query.strip():
        return []

    if not documents:
        return []

    if limit <= 0:
        return []

    reranker = get_reranker()

    pairs = [
        (query.strip(), document.page_content)
        for document in documents
    ]

    scores = reranker.predict(pairs)

    ranked_results = sorted(
        zip(documents, scores),
        key=lambda result: float(result[1]),
        reverse=True,
    )

    final_results = [
        (document, float(score))
        for document, score in ranked_results[:limit]
    ]

    logger.info(
        "[RERANKER] Candidates=%d Selected=%d",
        len(documents),
        len(final_results),
    )

    for rank, (document, score) in enumerate(final_results, start=1):
        logger.debug(
            "[RERANKER] Rank=%d Score=%.4f Source=%s Chunk=%s",
            rank,
            score,
            document.metadata.get("source"),
            document.metadata.get("chunk_id"),
        )

    return final_results
