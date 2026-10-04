from pathlib import Path

from langchain_chroma import Chroma

from chunk_documents import chunk_documents
from embeddings import get_embedding_model
from load_documents import load_documents


VECTOR_STORE_PATH = Path("vector_store")
COLLECTION_NAME = "learning_documents"


def get_vector_store() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embedding_model(),
        persist_directory=str(VECTOR_STORE_PATH),
    )


def get_existing_chunk_ids(vector_store: Chroma) -> set[str]:
    result = vector_store.get(
        include=[],
    )

    return set(result.get("ids", []))


def ingest_documents() -> None:
    documents = load_documents()

    if not documents:
        print("No supported documents found.")
        return

    chunks = chunk_documents(documents)

    if not chunks:
        print("No chunks generated.")
        return

    vector_store = get_vector_store()

    existing_ids = get_existing_chunk_ids(vector_store)

    new_chunks = []
    new_ids = []

    for chunk in chunks:
        chunk_id = str(chunk.metadata["chunk_id"])

        if chunk_id in existing_ids:
            continue

        new_chunks.append(chunk)
        new_ids.append(chunk_id)

    print(f"\nTotal chunks: {len(chunks)}")
    print(f"Existing chunks: {len(chunks) - len(new_chunks)}")
    print(f"New chunks: {len(new_chunks)}")

    if not new_chunks:
        print("\nVector store is already up to date.")
        return

    vector_store.add_documents(
        documents=new_chunks,
        ids=new_ids,
    )

    print(
        f"\nSuccessfully indexed {len(new_chunks)} new chunks."
    )


if __name__ == "__main__":
    ingest_documents()