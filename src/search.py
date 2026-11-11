
import logging

from langchain_chroma import Chroma
from langchain_core.documents import Document

from embeddings import get_embedding_model
from vector_store import COLLECTION_NAME, VECTOR_STORE_PATH


logger = logging.getLogger(__name__)

MAX_DISTANCE = 0.9


def get_vector_store() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embedding_model(),
        persist_directory=str(VECTOR_STORE_PATH),
    )


def search_documents(
    query: str,
    limit: int = 3,
    max_distance: float = MAX_DISTANCE,
    owner_id: str | None = None,
) -> list[tuple[Document, float]]:

    if not query or not query.strip():
        return []

    if not owner_id or not owner_id.strip():
        raise ValueError(
            "A valid owner_id is required for private document search."
        )

    if limit <= 0:
        return []

    if max_distance < 0:
        raise ValueError("max_distance cannot be negative.")

    results = get_vector_store().similarity_search_with_score(
        query=query,
        k=limit,
        filter={"owner_id": str(owner_id)},
    )

    matched_results = []

    for document, score in results:
        distance = float(score)

        logger.debug(
            "[VECTOR SEARCH] distance=%.4f owner=%s source=%s chunk_id=%s",
            distance,
            owner_id,
            document.metadata.get("source"),
            document.metadata.get("chunk_id"),
        )

        if distance <= max_distance:
            matched_results.append((document, distance))

    logger.info(
        "[VECTOR SEARCH] Retrieved=%d Accepted=%d Threshold=%.2f",
        len(results),
        len(matched_results),
        max_distance,
    )

    return matched_results
