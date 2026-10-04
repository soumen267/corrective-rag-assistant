from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


def load_file(file_path: Path) -> list[Document]:
    extension = file_path.suffix.lower()

    if extension in {".txt", ".md"}:
        loader = TextLoader(
            str(file_path),
            encoding="utf-8",
        )
    elif extension == ".pdf":
        loader = PyPDFLoader(str(file_path))
    else:
        return []

    documents = loader.load()

    for document in documents:
        document.metadata["source"] = file_path.as_posix()
        document.metadata["file_name"] = file_path.name
        document.metadata["file_type"] = extension.lstrip(".")

    return documents


def load_documents(data_directory: str = "data") -> list[Document]:
    directory = Path(data_directory)

    if not directory.exists():
        raise FileNotFoundError(
            f"Data directory does not exist: {directory}"
        )

    documents: list[Document] = []

    for file_path in sorted(directory.rglob("*")):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        print(f"Loading: {file_path}")

        documents.extend(load_file(file_path))

    return documents


if __name__ == "__main__":
    loaded_documents = load_documents()

    print(f"\nDocuments loaded: {len(loaded_documents)}")

    for document in loaded_documents:
        print("\n--- Document ---")
        print(document.page_content[:200])
        print(document.metadata)