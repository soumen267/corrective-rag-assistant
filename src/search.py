from langchain_chroma import Chroma
from langchain_core.documents import Document

from embeddings import get_embedding_model
from vector_store import COLLECTION_NAME, VECTOR_STORE_PATH


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
) -> list[tuple[Document, float]]:
    vector_store = get_vector_store()

    results = vector_store.similarity_search_with_score(
        query=query,
        k=limit,
    )

    return [
        (document, score)
        for document, score in results
        if score <= max_distance
    ]