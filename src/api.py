import os
import logging
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from sqlalchemy import delete, select
from auth_routes import router as auth_router
from auth import get_current_user
from fastapi import Depends
from database import Base, engine, SessionLocal
import user_models
import chat_models
import document_models
from contextlib import asynccontextmanager
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field

from conversation import ConversationHistory
from bm25_search import clear_bm25_cache
from knowledge_base import (
    delete_file_from_index,
    get_user_data_directory,
    index_file,
    list_knowledge_files,
)
from load_documents import SUPPORTED_EXTENSIONS
from rag_graph import ask_with_graph

from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024     # 1 MB


def validate_upload_content(file_path: Path, extension: str) -> None:
    """Validate basic file signatures/content after bounded upload."""
    if extension == ".pdf":
        with file_path.open("rb") as uploaded:
            header = uploaded.read(8)
        if not header.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is not a valid PDF.",
            )
        return

    # TXT and Markdown are text formats. Reject binary-looking or
    # non-UTF-8 files before passing them to document loaders.
    try:
        content = file_path.read_bytes()
        if b"\x00" in content:
            raise ValueError("Binary content detected.")
        content.decode("utf-8-sig")
    except (UnicodeDecodeError, ValueError, OSError) as exception:
        raise HTTPException(
            status_code=400,
            detail="The uploaded text file must contain valid UTF-8 text.",
        ) from exception



@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
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
app.include_router(auth_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response
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
# Persistent Session Management
# ---------------------------------------------------------


def get_or_create_session(
    session_id: str | None,
    owner: str,
) -> tuple[str, ConversationHistory]:
    """Load an owned session from MySQL or create a new one."""
    with SessionLocal() as db:
        if session_id:
            db_session = db.scalar(
                select(chat_models.ChatSession).where(
                    chat_models.ChatSession.session_id == session_id,
                    chat_models.ChatSession.owner_username == owner,
                )
            )

            # Use the same response for missing and foreign sessions.
            if db_session is None:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found.",
                )

            stored_messages = db.scalars(
                select(chat_models.ChatMessage)
                .where(chat_models.ChatMessage.session_id == session_id)
                .order_by(chat_models.ChatMessage.id.desc())
                .limit(10)
            ).all()

            history = ConversationHistory(max_messages=10)

            # The query is newest-first; restore chronological order.
            for message in reversed(stored_messages):
                if message.role == "user":
                    history.add_user_message(message.content)
                elif message.role == "assistant":
                    history.add_assistant_message(message.content)

            return session_id, history

        new_session_id = str(uuid4())

        db.add(
            chat_models.ChatSession(
                session_id=new_session_id,
                owner_username=owner,
            )
        )
        db.commit()

        return new_session_id, ConversationHistory(max_messages=10)


def save_chat_exchange(
    session_id: str,
    owner: str,
    question: str,
    answer: str,
) -> None:
    """Persist one completed user/assistant exchange."""
    with SessionLocal() as db:
        db_session = db.scalar(
            select(chat_models.ChatSession).where(
                chat_models.ChatSession.session_id == session_id,
                chat_models.ChatSession.owner_username == owner,
            )
        )

        if db_session is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found.",
            )

        db.add_all([
            chat_models.ChatMessage(
                session_id=session_id,
                role="user",
                content=question,
            ),
            chat_models.ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer,
            ),
        ])

        db_session.updated_at = datetime.utcnow()
        db.commit()


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness endpoint: confirms the API process is responding."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict[str, object]:
    """Dependency readiness check. Does not expose credentials or internals."""
    checks: dict[str, str] = {}
    try:
        from database import check_database_connection
        check_database_connection()
        checks["database"] = "ok"
    except Exception:
        logger.exception("Readiness check: database unavailable")
        checks["database"] = "error"

    try:
        from search import get_vector_store
        get_vector_store()._collection.count()
        checks["chroma"] = "ok"
    except Exception:
        logger.exception("Readiness check: Chroma unavailable")
        checks["chroma"] = "error"

    try:
        import json
        import os
        from urllib.request import urlopen
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        with urlopen(f"{ollama_url}/api/tags", timeout=3) as response:
            json.load(response)
        checks["ollama"] = "ok"
    except Exception:
        logger.warning("Readiness check: Ollama unavailable")
        checks["ollama"] = "error"

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


# ---------------------------------------------------------
# Chat
# ---------------------------------------------------------


@app.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    current_user: str = Depends(get_current_user),
) -> ChatResponse:
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Question cannot be empty.",
        )

    try:
        session_id, history = get_or_create_session(
            request.session_id,
            current_user,
        )

        answer, citations = ask_with_graph(
            question=question,
            history=history,
            owner_id=current_user,
        )

        # Save only the newly completed exchange. Older messages remain
        # in MySQL, while only the latest 10 are loaded into RAG context.
        save_chat_exchange(
            session_id=session_id,
            owner=current_user,
            question=question,
            answer=answer,
        )

    except HTTPException:
        raise

    except Exception as exception:
        logger.exception("Chat request failed")

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
    current_user: str = Depends(get_current_user),
) -> ClearSessionResponse:
    with SessionLocal() as db:
        db_session = db.scalar(
            select(chat_models.ChatSession).where(
                chat_models.ChatSession.session_id == session_id,
                chat_models.ChatSession.owner_username == current_user,
            )
        )

        if db_session is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found.",
            )

        # Preserve the session record, but permanently clear its messages.
        db.execute(
            delete(chat_models.ChatMessage).where(
                chat_models.ChatMessage.session_id == session_id
            )
        )
        db_session.updated_at = datetime.utcnow()
        db.commit()

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
    current_user: str = Depends(get_current_user),
) -> DocumentUploadResponse:
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File name is required.",
        )

    # Normalize the filename and prevent path traversal.
    original_name = file.filename.replace("\\", "/")
    safe_name = Path(original_name).name

    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(
            status_code=400,
            detail="Invalid file name.",
        )

    if len(safe_name) > 255:
        raise HTTPException(
            status_code=400,
            detail="File name must be 255 characters or fewer.",
        )

    extension = Path(safe_name).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed: .txt, .md, .pdf",
        )

    user_directory = get_user_data_directory(current_user)
    user_directory.mkdir(parents=True, exist_ok=True)

    # A temporary unique path prevents overwriting the current version.
    stored_name = f"{uuid4().hex}{extension}"
    destination = user_directory / stored_name

    total_bytes = 0
    indexing_succeeded = False
    file_hash = None

    try:
        with destination.open("xb") as buffer:
            while True:
                chunk = file.file.read(UPLOAD_CHUNK_SIZE)

                if not chunk:
                    break

                total_bytes += len(chunk)

                if total_bytes > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB upload limit.",
                    )

                buffer.write(chunk)

        validate_upload_content(destination, extension)

        # Hash the completed upload. Files are capped at 10 MB.
        file_hash = sha256(destination.read_bytes()).hexdigest()

        with SessionLocal() as db:
            existing_document = db.scalar(
                select(document_models.UserDocument).where(
                    document_models.UserDocument.owner_username == current_user,
                    document_models.UserDocument.original_filename == safe_name,
                )
            )

            # Identical content: retain the existing index and stored file.
            if (
                existing_document is not None
                and existing_document.file_hash == file_hash
            ):
                existing_source = existing_document.stored_path
                destination.unlink(missing_ok=True)

                return DocumentUploadResponse(
                    file_name=safe_name,
                    source=existing_source,
                    chunks_indexed=0,
                    message="Document is unchanged. Existing index was retained.",
                )

            # Index the new version before removing the previous version.
            chunks_indexed = index_file(destination, owner_id=current_user)
            clear_bm25_cache(current_user)

            if chunks_indexed <= 0:
                raise RuntimeError("No document chunks were indexed.")

            indexing_succeeded = True

            if existing_document is None:
                db.add(
                    document_models.UserDocument(
                        owner_username=current_user,
                        original_filename=safe_name,
                        stored_path=destination.as_posix(),
                        file_hash=file_hash,
                        version=1,
                    )
                )
                version_message = "Document indexed successfully."
            else:
                old_path = Path(existing_document.stored_path)

                existing_document.stored_path = destination.as_posix()
                existing_document.file_hash = file_hash
                existing_document.version += 1
                version_message = (
                    f"Document updated successfully. Version: "
                    f"{existing_document.version}."
                )

            # Commit the registry first. The new index already exists, so a
            # failed DB commit leaves the old version intact.
            db.commit()

            if existing_document is not None:
                # Clean up the previous index only after the registry points
                # to the new version. A cleanup failure leaves stale vectors,
                # but does not make the new document unavailable.
                try:
                    delete_file_from_index(old_path, owner_id=current_user)
                except Exception:
                    logger.exception(
                        "New version is active, but old Chroma chunks remain: %s",
                        old_path,
                    )

                try:
                    if old_path.exists():
                        old_path.unlink()
                except OSError:
                    logger.exception(
                        "New document version indexed, but old file cleanup failed: %s",
                        old_path,
                    )

        return DocumentUploadResponse(
            file_name=safe_name,
            source=destination.as_posix(),
            chunks_indexed=chunks_indexed,
            message=version_message,
        )

    except HTTPException:
        raise

    except Exception as exception:
        logger.exception("Document upload/indexing failed")

        # Best-effort cleanup of the newly uploaded source and its chunks.
        try:
            delete_file_from_index(destination, owner_id=current_user)
        except Exception:
            logger.exception("New document index cleanup failed")

        try:
            if destination.exists():
                destination.unlink()
        except OSError:
            logger.exception("New uploaded file cleanup failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to upload and index document.",
        ) from exception

    finally:
        file.file.close()


@app.get(
    "/documents",
    response_model=DocumentListResponse,
)
def get_documents(current_user: str = Depends(get_current_user),) -> DocumentListResponse:
    return DocumentListResponse(
        documents=list_knowledge_files(owner_id=current_user)
    )



@app.delete(
    "/documents",
    response_model=DocumentDeleteResponse,
)
def delete_document(
    source: str,
    current_user: str = Depends(get_current_user),
) -> DocumentDeleteResponse:
    # Resolve this user's private knowledge directory.
    data_directory = get_user_data_directory(current_user).resolve()

    # Resolve the requested path safely.
    try:
        requested_path = Path(source).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid document path.",
        ) from exception

    # Only allow files directly inside DATA_DIRECTORY.
    if requested_path.parent != data_directory:
        raise HTTPException(
            status_code=400,
            detail="Document must be directly inside the knowledge directory.",
        )

    if not requested_path.is_file():
        raise HTTPException(
            status_code=400,
            detail="Source is not a regular file.",
        )

    if requested_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported document type.",
        )

    try:
        # Remove indexed chunks before deleting the physical file.
        delete_file_from_index(requested_path, owner_id=current_user)
        clear_bm25_cache(current_user)
        requested_path.unlink()

        with SessionLocal() as db:
            document_record = db.scalar(
                select(document_models.UserDocument).where(
                    document_models.UserDocument.owner_username == current_user,
                    document_models.UserDocument.stored_path == requested_path.as_posix(),
                )
            )
            if document_record is not None:
                db.delete(document_record)
                db.commit()

    except Exception as exception:
        logger.exception("Document deletion failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to delete document.",
        ) from exception

    return DocumentDeleteResponse(
        source=requested_path.as_posix(),
        message="Document deleted successfully.",
    )
