"""Pydantic v2 request/response models. Route handlers never return ORM objects directly;
everything crossing the wire goes through one of these.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from copilot_api.models import CaseStatus, CaseType, ListingStatus, OrderStatus


class ApiModel(BaseModel):
    """Base for request bodies: unknown fields are rejected, not silently dropped."""

    model_config = ConfigDict(extra="forbid")


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- /v1/me ---


class MeResponse(ResponseModel):
    seller_id: uuid.UUID
    email: str
    display_name: str
    roles: list[str]


# --- /v1/listings ---


class ListingResponse(ResponseModel):
    id: uuid.UUID
    sku: str
    title: str
    price_cents: int
    status: ListingStatus
    created_at: datetime


# --- /v1/orders ---


class OrderItemResponse(ResponseModel):
    listing_id: uuid.UUID
    quantity: int
    unit_price_cents: int


class OrderResponse(ResponseModel):
    id: uuid.UUID
    buyer_ref: str
    status: OrderStatus
    total_cents: int
    currency: str
    placed_at: datetime
    delivered_at: datetime | None
    updated_at: datetime
    items: list[OrderItemResponse]


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: str | None


class RefundRequestBody(ApiModel):
    reason: Annotated[str, Field(min_length=10, max_length=1000)]


# --- /v1/cases ---


class SupportCaseResponse(ResponseModel):
    id: uuid.UUID
    order_id: uuid.UUID | None
    type: CaseType
    status: CaseStatus
    description: str
    created_at: datetime


class CaseListResponse(BaseModel):
    items: list[SupportCaseResponse]


# --- /v1/chat ---


class ChatSessionCreateBody(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]


class ChatSessionResponse(BaseModel):
    session_id: str
    seller_id: str
    title: str
    created_at: datetime
    last_message_at: datetime


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse]
    next_cursor: str | None


class ChatMessageResponse(BaseModel):
    session_id: str
    message_id: str
    role: str
    content: str
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
    next_cursor: str | None


# --- /v1/admin/cases ---


class AdminCaseUpdateBody(ApiModel):
    status: CaseStatus
