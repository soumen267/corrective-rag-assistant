import logging
import re
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from chunk_documents import chunk_documents
from knowledge_base import get_user_data_directory
from load_documents import SUPPORTED_EXTENSIONS, load_documents

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or",
    "that", "the", "this", "to", "what", "when", "where",
    "which", "who", "why", "with",
}


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"\b\w+\b", text.lower())
        if token not in STOP_WORDS
    ]


def _directory_fingerprint(directory: Path) -> tuple[tuple[str, int, int], ...]:
    """Detect additions, removals and modifications in one user's files."""
    if not directory.exists():
        return ()
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            stat = path.stat()
            entries.append((path.as_posix(), stat.st_size, stat.st_mtime_ns))
    return tuple(entries)


@lru_cache(maxsize=64)
def _build_owner_index(
    owner_id: str,
    fingerprint: tuple[tuple[str, int, int], ...],
):
    """Build one cached BM25 index per owner and file-state fingerprint."""
    directory = get_user_data_directory(owner_id)
    if not fingerprint:
        return (), (), None

    raw_documents = load_documents(str(directory))
    chunks = chunk_documents(raw_documents)
    for chunk in chunks:
        chunk.metadata["owner_id"] = owner_id

    chunk_tokens = tuple(tuple(tokenize(chunk.page_content)) for chunk in chunks)
    index = BM25Okapi([list(tokens) for tokens in chunk_tokens]) if any(chunk_tokens) else None
    logger.info("[BM25] Built owner index: owner=%s chunks=%d", owner_id, len(chunks))
    return tuple(chunks), chunk_tokens, index


def clear_bm25_cache(owner_id: str | None = None) -> None:
    """Clear cached BM25 indexes. Call after document mutations."""
    # Fingerprints also make stale entries unreachable after file changes.
    # lru_cache has no selective deletion API, so clear the bounded cache.
    _build_owner_index.cache_clear()
    logger.info("[BM25] Cache cleared%s", f" for owner={owner_id}" if owner_id else "")


class BM25Search:
    def __init__(self, owner_id: str) -> None:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("A valid owner_id is required for private BM25 search.")
        self.owner_id = owner_id.strip()
        directory = get_user_data_directory(self.owner_id)
        fingerprint = _directory_fingerprint(directory)
        self.chunks, self.chunk_tokens, self.index = _build_owner_index(
            self.owner_id, fingerprint
        )

    def search(self, query: str, limit: int = 5) -> list[tuple[Document, float]]:
        if not query or not query.strip() or self.index is None or limit <= 0:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self.index.get_scores(query_tokens)
        query_token_set = set(query_tokens)
        matching_results = [
            (document, float(score))
            for document, document_tokens, score in zip(self.chunks, self.chunk_tokens, scores)
            if query_token_set.intersection(document_tokens)
        ]
        return sorted(matching_results, key=lambda item: item[1], reverse=True)[:limit]
