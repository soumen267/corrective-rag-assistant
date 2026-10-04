import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field

from conversation import ConversationHistory
from knowledge_base import (
    DATA_DIRECTORY,
    delete_file_from_index,
    index_file,
    list_knowledge_files,
)
from load_documents import SUPPORTED_EXTENSIONS
from rag_graph import ask_with_graph
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Local RAG API",
    description=(
        "Conversational RAG API using Chroma, BM25, "
        "cross-encoder reranking and Ollama."
    ),
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------


class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
    )
    session_id: str | None = None


class CitationResponse(BaseModel):
    source: str
    file_name: str
    file_type: str
    page: int | None
    chunk_id: str
    relevance_score: float
    excerpt: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[CitationResponse]


class ClearSessionResponse(BaseModel):
    session_id: str
    message: str


class DocumentUploadResponse(BaseModel):
    file_name: str
    source: str
    chunks_indexed: int
    message: str


class DocumentListResponse(BaseModel):
    documents: list[str]


class DocumentDeleteResponse(BaseModel):
    source: str
    message: str


# ---------------------------------------------------------
# Session Management
# ---------------------------------------------------------


sessions: dict[str, ConversationHistory] = {}
sessions_lock = Lock()


def get_or_create_session(
    session_id: str | None,
) -> tuple[str, ConversationHistory]:
    if session_id:
        with sessions_lock:
            history = sessions.get(session_id)

        if history is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found.",
            )

        return session_id, history

    new_session_id = str(uuid4())

    history = ConversationHistory(
        max_messages=10,
    )

    with sessions_lock:
        sessions[new_session_id] = history

    return new_session_id, history


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


# ---------------------------------------------------------
# Chat
# ---------------------------------------------------------


@app.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
) -> ChatResponse:
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Question cannot be empty.",
        )

    session_id, history = get_or_create_session(
        request.session_id
    )

    try:
        answer, citations = ask_with_graph(
            question=question,
            history=history,
        )

    except Exception as exception:
        print(f"Chat error: {exception}")

        raise HTTPException(
            status_code=500,
            detail="Unable to process the question.",
        ) from exception

    citation_responses = [
        CitationResponse(
            source=citation.source,
            file_name=citation.file_name,
            file_type=citation.file_type,
            page=citation.page,
            chunk_id=citation.chunk_id,
            relevance_score=citation.relevance_score,
            excerpt=citation.excerpt,
        )
        for citation in citations
    ]

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        sources=citation_responses,
    )


# ---------------------------------------------------------
# Sessions
# ---------------------------------------------------------


@app.delete(
    "/sessions/{session_id}",
    response_model=ClearSessionResponse,
)
def clear_session(
    session_id: str,
) -> ClearSessionResponse:
    with sessions_lock:
        history = sessions.get(session_id)

    if history is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found.",
        )

    history.clear()

    return ClearSessionResponse(
        session_id=session_id,
        message="Conversation history cleared.",
    )


# ---------------------------------------------------------
# Documents
# ---------------------------------------------------------


@app.post(
    "/documents",
    response_model=DocumentUploadResponse,
)
def upload_document(
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File name is required.",
        )

    safe_name = Path(
        file.filename
    ).name

    extension = Path(
        safe_name
    ).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Allowed: .txt, .md, .pdf"
            ),
        )

    DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        DATA_DIRECTORY / safe_name
    )

    try:
        with destination.open("wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer,
            )

        chunks_indexed = index_file(
            destination
        )

    except Exception as exception:
        if destination.exists():
            destination.unlink()

        raise HTTPException(
            status_code=500,
            detail="Unable to index document.",
        ) from exception

    finally:
        file.file.close()

    return DocumentUploadResponse(
        file_name=safe_name,
        source=destination.as_posix(),
        chunks_indexed=chunks_indexed,
        message="Document indexed successfully.",
    )


@app.get(
    "/documents",
    response_model=DocumentListResponse,
)
def get_documents() -> DocumentListResponse:
    return DocumentListResponse(
        documents=list_knowledge_files()
    )


@app.delete(
    "/documents",
    response_model=DocumentDeleteResponse,
)
def delete_document(
    source: str,
) -> DocumentDeleteResponse:
    file_path = Path(source)

    try:
        resolved_data_directory = (
            DATA_DIRECTORY.resolve()
        )

        resolved_file = (
            file_path.resolve()
        )

        resolved_file.relative_to(
            resolved_data_directory
        )

    except ValueError as exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid document path.",
        ) from exception

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=400,
            detail="Source is not a file.",
        )

    if (
        file_path.suffix.lower()
        not in SUPPORTED_EXTENSIONS
    ):
        raise HTTPException(
            status_code=400,
            detail="Unsupported document type.",
        )

    try:
        delete_file_from_index(
            file_path
        )

        file_path.unlink()

    except Exception as exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to delete document.",
        ) from exception

    return DocumentDeleteResponse(
        source=file_path.as_posix(),
        message="Document deleted successfully.",
    )