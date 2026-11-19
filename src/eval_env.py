"""Isolated, reproducible index for retrieval evaluation.

The evaluation corpus is copied into a temporary per-user directory and
indexed into a temporary Chroma store. The application's real data,
vector store and database are never read or modified, so results depend
only on the corpus, the questions and the models.
"""

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import knowledge_base
import search
import vector_store
from bm25_search import clear_bm25_cache

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIRECTORY = PROJECT_ROOT / "eval" / "corpus"
QUESTIONS_FILE = PROJECT_ROOT / "eval" / "retrieval_questions.json"
EVAL_OWNER_ID = "eval-user"


def load_questions(path: Path = QUESTIONS_FILE) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def source_name(source: str) -> str:
    """Reduce a stored source path to its file name for comparison."""
    return Path(source.replace("\\", "/")).name


@contextmanager
def isolated_eval_index(
    corpus_directory: Path = CORPUS_DIRECTORY,
    owner_id: str = EVAL_OWNER_ID,
) -> Iterator[str]:
    """Index the corpus into a temporary store and yield the eval owner ID."""
    files = sorted(
        path
        for path in corpus_directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in knowledge_base.SUPPORTED_EXTENSIONS
    )

    if not files:
        raise FileNotFoundError(f"No corpus files found in {corpus_directory}")

    original_data_directory = knowledge_base.DATA_DIRECTORY
    original_vector_path = vector_store.VECTOR_STORE_PATH
    original_search_path = search.VECTOR_STORE_PATH

    # Windows keeps SQLite handles open briefly; tolerate cleanup failures.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        temp_path = Path(temp)

        knowledge_base.DATA_DIRECTORY = temp_path / "data"
        vector_store.VECTOR_STORE_PATH = temp_path / "vector_store"
        search.VECTOR_STORE_PATH = vector_store.VECTOR_STORE_PATH
        clear_bm25_cache()

        try:
            user_directory = knowledge_base.get_user_data_directory(owner_id)
            user_directory.mkdir(parents=True)

            chunk_total = 0
            for file in files:
                copied = user_directory / file.name
                shutil.copyfile(file, copied)
                chunk_total += knowledge_base.index_file(copied, owner_id=owner_id)

            print(
                f"Indexed {len(files)} documents into {chunk_total} chunks "
                f"(isolated temporary store)."
            )

            yield owner_id

        finally:
            knowledge_base.DATA_DIRECTORY = original_data_directory
            vector_store.VECTOR_STORE_PATH = original_vector_path
            search.VECTOR_STORE_PATH = original_search_path
            clear_bm25_cache()
