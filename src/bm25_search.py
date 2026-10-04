import re

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from chunk_documents import chunk_documents
from load_documents import load_documents


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"\b\w+\b", text.lower())

    return [
        token
        for token in tokens
        if token not in STOP_WORDS
    ]


class BM25Search:
    def __init__(self) -> None:
        documents = load_documents()
        self.chunks = chunk_documents(documents)

        tokenized_chunks = [
            tokenize(chunk.page_content)
            for chunk in self.chunks
        ]

        self.index = BM25Okapi(tokenized_chunks)

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[tuple[Document, float]]:
        if not query.strip():
            return []

        query_tokens = tokenize(query)

        if not query_tokens:
            return []

        scores = self.index.get_scores(query_tokens)

        ranked_results = sorted(
            zip(self.chunks, scores),
            key=lambda result: result[1],
            reverse=True,
        )

        return [
            (document, float(score))
            for document, score in ranked_results[:limit]
            if score > 0
        ]


if __name__ == "__main__":
    search_engine = BM25Search()

    query = input("Enter search query: ").strip()

    results = search_engine.search(
        query=query,
        limit=5,
    )

    print(f"\nQuery: {query}")
    print("=" * 60)

    if not results:
        print("No BM25 matches found.")

    for index, (document, score) in enumerate(
        results,
        start=1,
    ):
        print(f"\nResult {index}")
        print(f"BM25 Score: {score:.4f}")
        print(f"Source: {document.metadata.get('source')}")
        print("\nContent:")
        print(document.page_content)
        print("-" * 60)