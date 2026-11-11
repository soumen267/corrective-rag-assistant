from collections import defaultdict

from langchain_core.documents import Document

from bm25_search import BM25Search
from search import search_documents

VECTOR_LIMIT = 5
BM25_LIMIT = 5
FINAL_LIMIT = 10
RRF_K = 60


def get_document_id(document: Document) -> str:
    chunk_id = document.metadata.get("chunk_id")
    return str(chunk_id) if chunk_id else document.page_content


def reciprocal_rank(rank: int) -> float:
    return 1.0 / (RRF_K + rank)


def hybrid_search(
    query: str,
    limit: int = FINAL_LIMIT,
    owner_id: str | None = None,
) -> list[tuple[Document, float]]:
    if not query.strip():
        return []
    if owner_id is None:
        raise ValueError("owner_id is required for private hybrid search.")

    vector_results = search_documents(
        query=query,
        limit=VECTOR_LIMIT,
        owner_id=owner_id,
    )
    bm25_results = BM25Search(owner_id=owner_id).search(
        query=query,
        limit=BM25_LIMIT,
    )

    combined_scores: dict[str, float] = defaultdict(float)
    documents: dict[str, Document] = {}

    for results in (vector_results, bm25_results):
        for rank, (document, _score) in enumerate(results, start=1):
            document_id = get_document_id(document)
            documents[document_id] = document
            combined_scores[document_id] += reciprocal_rank(rank)

    ranked_ids = sorted(
        combined_scores,
        key=combined_scores.get,
        reverse=True,
    )
    return [
        (documents[doc_id], combined_scores[doc_id])
        for doc_id in ranked_ids[:limit]
    ]
