from pathlib import Path

from chunk_documents import chunk_documents
from load_documents import (
    SUPPORTED_EXTENSIONS,
    load_file,
)
from vector_store import get_vector_store


DATA_DIRECTORY = Path("data")


def normalize_source(file_path: Path) -> str:
    return file_path.as_posix()


def validate_file(file_path: Path) -> None:
    extension = file_path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension}"
        )


def index_file(
    file_path: Path,
) -> int:
    """
    Index one file.

    Existing chunks belonging to the same source are
    deleted first, preventing stale chunks when a file
    is updated.
    """
    validate_file(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    source = normalize_source(file_path)

    documents = load_file(file_path)

    chunks = chunk_documents(documents)

    vector_store = get_vector_store()

    # Remove previous version of this source.
    vector_store.delete(
        where={
            "source": source,
        }
    )

    if not chunks:
        return 0

    ids = [
        str(chunk.metadata["chunk_id"])
        for chunk in chunks
    ]

    vector_store.add_documents(
        documents=chunks,
        ids=ids,
    )

    return len(chunks)


def delete_file_from_index(
    file_path: Path,
) -> None:
    """
    Delete all Chroma chunks associated with a file.
    """
    source = normalize_source(file_path)

    vector_store = get_vector_store()

    vector_store.delete(
        where={
            "source": source,
        }
    )


def list_knowledge_files() -> list[str]:
    """
    Return supported files currently present
    in the data directory.
    """
    if not DATA_DIRECTORY.exists():
        return []

    files = []

    for file_path in sorted(
        DATA_DIRECTORY.rglob("*")
    ):
        if not file_path.is_file():
            continue

        if (
            file_path.suffix.lower()
            not in SUPPORTED_EXTENSIONS
        ):
            continue

        files.append(
            normalize_source(file_path)
        )

    return files