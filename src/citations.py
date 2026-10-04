from dataclasses import dataclass

from langchain_core.documents import Document


@dataclass
class Citation:
    source: str
    file_name: str
    file_type: str
    page: int | None
    chunk_id: str
    relevance_score: float
    excerpt: str


def create_citation(
    document: Document,
    score: float,
    excerpt_length: int = 250,
) -> Citation:
    metadata = document.metadata

    content = document.page_content.strip()

    if len(content) > excerpt_length:
        excerpt = (
            content[:excerpt_length].rstrip()
            + "..."
        )
    else:
        excerpt = content

    page = metadata.get("page")

    if page is not None:
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = None

    return Citation(
        source=str(
            metadata.get("source", "Unknown")
        ),
        file_name=str(
            metadata.get("file_name", "Unknown")
        ),
        file_type=str(
            metadata.get("file_type", "Unknown")
        ),
        page=page,
        chunk_id=str(
            metadata.get("chunk_id", "Unknown")
        ),
        relevance_score=float(score),
        excerpt=excerpt,
    )


def create_citations(
    search_results: list[
        tuple[Document, float]
    ],
) -> list[Citation]:
    return [
        create_citation(
            document=document,
            score=score,
        )
        for document, score in search_results
    ]