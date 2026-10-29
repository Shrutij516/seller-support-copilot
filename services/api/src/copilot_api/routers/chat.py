import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request

from copilot_api.auth import require_seller
from copilot_api.config import Settings, get_settings
from copilot_api.dynamo.chat_repository import (
    ChatMessage,
    ChatRepository,
    Citation,
    SessionNotFoundError,
)
from copilot_api.errors import not_found, service_unavailable
from copilot_api.rag.prompt import (
    REFUSAL_MESSAGE,
    SYSTEM_PROMPT,
    build_user_message,
    filter_by_min_score,
    make_citations,
)
from copilot_api.rag.types import Generator, RagBackendError, Retriever
from copilot_api.schemas import (
    ChatMessageCreateBody,
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSessionCreateBody,
    ChatSessionListResponse,
    ChatSessionResponse,
    CitationResponse,
)

router = APIRouter(prefix="/v1/chat", tags=["chat"])

logger = logging.getLogger(__name__)


def get_chat_repo(request: Request) -> ChatRepository:
    repo: ChatRepository = request.app.state.chat_repo
    return repo


def get_retriever(request: Request) -> Retriever:
    retriever: Retriever = request.app.state.retriever
    return retriever


def get_generator(request: Request) -> Generator:
    generator: Generator = request.app.state.generator
    return generator


def _message_response(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        session_id=message.session_id,
        message_id=message.message_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        citations=[
            CitationResponse(index=c.index, source=c.source, snippet=c.snippet)
            for c in message.citations
        ],
    )


async def _append(
    repo: ChatRepository,
    session_id: str,
    role: str,
    content: str,
    citations: tuple[Citation, ...] = (),
) -> ChatMessage:
    try:
        return await repo.append_message(session_id, role, content, citations=citations)
    except SessionNotFoundError as exc:
        # Expired between the ownership check and this write: same answer as never existing.
        raise not_found("chat session not found") from exc


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
async def create_chat_session(
    body: ChatSessionCreateBody,
    seller_id: uuid.UUID = Depends(require_seller),
    repo: ChatRepository = Depends(get_chat_repo),
) -> ChatSessionResponse:
    session = await repo.create_session(str(seller_id), title=body.title)
    return ChatSessionResponse(
        session_id=session.session_id,
        seller_id=session.seller_id,
        title=session.title,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    seller_id: uuid.UUID = Depends(require_seller),
    repo: ChatRepository = Depends(get_chat_repo),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ChatSessionListResponse:
    page = await repo.list_sessions_for_seller(str(seller_id), limit=limit, cursor=cursor)
    return ChatSessionListResponse(
        items=[
            ChatSessionResponse(
                session_id=s.session_id,
                seller_id=s.seller_id,
                title=s.title,
                created_at=s.created_at,
                last_message_at=s.last_message_at,
            )
            for s in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/sessions/{session_id}/messages", response_model=ChatMessageListResponse)
async def list_chat_messages(
    session_id: str,
    seller_id: uuid.UUID = Depends(require_seller),
    repo: ChatRepository = Depends(get_chat_repo),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ChatMessageListResponse:
    owned_session = await repo.get_session(session_id)
    if owned_session is None or owned_session.seller_id != str(seller_id):
        raise not_found("chat session not found")

    page = await repo.list_messages(session_id, limit=limit, cursor=cursor)
    return ChatMessageListResponse(
        items=[_message_response(m) for m in page.items], next_cursor=page.next_cursor
    )


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse, status_code=201)
async def post_chat_message(
    session_id: str,
    body: ChatMessageCreateBody,
    seller_id: uuid.UUID = Depends(require_seller),
    repo: ChatRepository = Depends(get_chat_repo),
    retriever: Retriever = Depends(get_retriever),
    generator: Generator = Depends(get_generator),
    settings: Settings = Depends(get_settings),
) -> ChatMessageResponse:
    """Store the seller's question, answer it from the policy knowledge base, store and
    return the answer. The question is stored even if answering fails (a 503 leaves the user
    message in place and no assistant message), so the thread shows what was asked.
    """
    owned_session = await repo.get_session(session_id)
    if owned_session is None or owned_session.seller_id != str(seller_id):
        raise not_found("chat session not found")

    await _append(repo, session_id, "user", body.content)

    try:
        chunks = filter_by_min_score(await retriever.retrieve(body.content), settings.rag_min_score)
        if not chunks:
            refusal = await _append(repo, session_id, "assistant", REFUSAL_MESSAGE)
            return _message_response(refusal)
        answer = await generator.generate(SYSTEM_PROMPT, build_user_message(body.content, chunks))
    except RagBackendError as exc:
        # request_id is attached to every log line by JsonFormatter.
        logger.warning(
            "chat answer unavailable",
            extra={"stage": exc.stage, "reason": exc.reason, "session_id": session_id},
        )
        raise service_unavailable(
            "the assistant is temporarily unavailable; please try again shortly"
        ) from exc

    assistant = await _append(
        repo, session_id, "assistant", answer, citations=make_citations(chunks)
    )
    return _message_response(assistant)
