import uuid

from fastapi import APIRouter, Depends, Query, Request

from copilot_api.auth import require_seller
from copilot_api.dynamo.chat_repository import ChatRepository
from copilot_api.errors import not_found
from copilot_api.schemas import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSessionCreateBody,
    ChatSessionListResponse,
    ChatSessionResponse,
)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


def get_chat_repo(request: Request) -> ChatRepository:
    repo: ChatRepository = request.app.state.chat_repo
    return repo


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
        items=[
            ChatMessageResponse(
                session_id=m.session_id,
                message_id=m.message_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in page.items
        ],
        next_cursor=page.next_cursor,
    )
