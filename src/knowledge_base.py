from hashlib import sha256
from pathlib import Path

from chunk_documents import chunk_documents
from load_documents import SUPPORTED_EXTENSIONS, load_file
from vector_store import get_vector_store

DATA_DIRECTORY = Path("data")


def normalize_source(file_path: Path) -> str:
    return file_path.as_posix()


def get_user_data_directory(owner_id: str) -> Path:
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("A valid owner ID is required.")
    owner_key = sha256(owner_id.encode("utf-8")).hexdigest()
    return DATA_DIRECTORY / "users" / owner_key


def validate_file(file_path: Path) -> None:
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")


def index_file(file_path: Path, owner_id: str | None = None) -> int:
    validate_file(file_path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    if owner_id is None:
        raise ValueError("owner_id is required for document indexing.")

    source = normalize_source(file_path)
    documents = load_file(file_path)
    chunks = chunk_documents(documents)
    if not chunks:
        return 0

    owner = str(owner_id)
    for chunk in chunks:
        chunk.metadata["source"] = source
        chunk.metadata["owner_id"] = owner

    ids = [str(chunk.metadata["chunk_id"]) for chunk in chunks]
    vector_store = get_vector_store()
    vector_store.add_documents(documents=chunks, ids=ids)

    existing = vector_store.get(
        where={"$and": [{"source": source}, {"owner_id": owner}]},
        include=[],
    )
    stale_ids = set(existing.get("ids", [])).difference(ids)
    if stale_ids:
        vector_store.delete(ids=list(stale_ids))
    return len(chunks)


def delete_file_from_index(file_path: Path, owner_id: str | None = None) -> None:
    if owner_id is None:
        raise ValueError("owner_id is required for index deletion.")
    get_vector_store().delete(
        where={
            "$and": [
                {"source": normalize_source(file_path)},
                {"owner_id": str(owner_id)},
            ]
        }
    )


def list_knowledge_files(owner_id: str | None = None) -> list[str]:
    if owner_id is None:
        return []
    directory = get_user_data_directory(owner_id)
    if not directory.exists():
        return []

    return [
        normalize_source(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
