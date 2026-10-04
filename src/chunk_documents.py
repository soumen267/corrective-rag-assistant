from hashlib import sha256

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


CHUNK_SIZE = 500
CHUNK_OVERLAP = 100


def generate_chunk_id(document: Document) -> str:
    """
    Generate a deterministic chunk ID from the source,
    page and chunk content.
    """
    source = str(
        document.metadata.get(
            "source",
            "unknown",
        )
    )

    page = str(
        document.metadata.get(
            "page",
            "none",
        )
    )

    raw_id = (
        f"{source}:"
        f"{page}:"
        f"{document.page_content}"
    )

    return sha256(
        raw_id.encode("utf-8")
    ).hexdigest()


def chunk_documents(
    documents: list[Document],
) -> list[Document]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    chunks = text_splitter.split_documents(
        documents
    )

    for chunk in chunks:
        chunk.metadata["chunk_id"] = (
            generate_chunk_id(chunk)
        )

    return chunks