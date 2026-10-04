from collections import defaultdict

from langchain_core.documents import Document

from bm25_search import BM25Search
from search import search_documents


VECTOR_LIMIT = 5
BM25_LIMIT = 5
FINAL_LIMIT = 10

RRF_K = 60


def get_document_id(document: Document) -> str:
    """
    Return a stable identifier for a document chunk.
    """
    chunk_id = document.metadata.get("chunk_id")

    if chunk_id:
        return str(chunk_id)

    return document.page_content


def reciprocal_rank(rank: int) -> float:
    """
    Calculate the Reciprocal Rank Fusion contribution
    for a given ranking position.
    """
    return 1.0 / (RRF_K + rank)


def hybrid_search(
    query: str,
    limit: int = FINAL_LIMIT,
) -> list[tuple[Document, float]]:
    """
    Combine vector retrieval and BM25 retrieval using
    Reciprocal Rank Fusion.
    """
    if not query.strip():
        return []

    vector_results = search_documents(
        query=query,
        limit=VECTOR_LIMIT,
    )

    bm25_engine = BM25Search()

    bm25_results = bm25_engine.search(
        query=query,
        limit=BM25_LIMIT,
    )

    combined_scores: dict[str, float] = defaultdict(float)
    documents: dict[str, Document] = {}

    # Vector search rankings
    for rank, (document, _score) in enumerate(
        vector_results,
        start=1,
    ):
        document_id = get_document_id(document)

        documents[document_id] = document
        combined_scores[document_id] += reciprocal_rank(rank)

    # BM25 rankings
    for rank, (document, _score) in enumerate(
        bm25_results,
        start=1,
    ):
        document_id = get_document_id(document)

        documents[document_id] = document
        combined_scores[document_id] += reciprocal_rank(rank)

    ranked_document_ids = sorted(
        combined_scores,
        key=combined_scores.get,
        reverse=True,
    )

    return [
        (
            documents[document_id],
            combined_scores[document_id],
        )
        for document_id in ranked_document_ids[:limit]
    ]


def main() -> None:
    query = input("Enter search query: ").strip()

    results = hybrid_search(
        query=query,
        limit=FINAL_LIMIT,
    )

    print(f"\nQuery: {query}")
    print("=" * 60)

    if not results:
        print("No relevant documents found.")
        return

    for index, (document, score) in enumerate(
        results,
        start=1,
    ):
        print(f"\nResult {index}")
        print(f"Hybrid Score: {score:.6f}")
        print(f"Source: {document.metadata.get('source')}")
        print(f"Chunk ID: {document.metadata.get('chunk_id')}")

        print("\nContent:")
        print(document.page_content)

        print("-" * 60)


if __name__ == "__main__":
    main()