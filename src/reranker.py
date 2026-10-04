from functools import lru_cache

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder


RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """
    Load the cross-encoder once and reuse it.
    """
    return CrossEncoder(RERANKER_MODEL)


def rerank_documents(
    query: str,
    documents: list[Document],
    limit: int = 3,
) -> list[tuple[Document, float]]:
    """
    Rerank candidate documents according to their
    relevance to the query.
    """
    if not query.strip() or not documents:
        return []

    reranker = get_reranker()

    pairs = [
        (query, document.page_content)
        for document in documents
    ]

    scores = reranker.predict(pairs)

    ranked_results = sorted(
        zip(documents, scores),
        key=lambda result: float(result[1]),
        reverse=True,
    )

    return [
        (document, float(score))
        for document, score in ranked_results[:limit]
    ]
if __name__ == "__main__":
    from hybrid_search import hybrid_search

    query = input("Enter search query: ").strip()

    hybrid_results = hybrid_search(
        query=query,
        limit=10,
    )

    candidates = [
        document
        for document, _score in hybrid_results
    ]

    results = rerank_documents(
        query=query,
        documents=candidates,
        limit=3,
    )

    print(f"\nQuery: {query}")
    print("=" * 60)

    if not results:
        print("No relevant documents found.")

    for index, (document, score) in enumerate(
        results,
        start=1,
    ):
        print(f"\nResult {index}")
        print(f"Reranker Score: {score:.4f}")
        print(f"Source: {document.metadata.get('source')}")
        print(f"Chunk ID: {document.metadata.get('chunk_id')}")

        print("\nContent:")
        print(document.page_content)

        print("-" * 60)