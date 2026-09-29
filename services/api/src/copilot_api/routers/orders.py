import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from copilot_api.auth import require_seller
from copilot_api.deps import get_db_session
from copilot_api.errors import conflict, not_found, unprocessable
from copilot_api.models import Order, OrderItem, OrderStatus
from copilot_api.pagination import decode_orders_cursor, encode_orders_cursor
from copilot_api.schemas import (
    OrderItemResponse,
    OrderListResponse,
    OrderResponse,
    RefundRequestBody,
    SupportCaseResponse,
)
from copilot_api.services.refunds import (
    AlreadyRequested,
    NotEligible,
    OrderNotFound,
    request_refund,
)

router = APIRouter(prefix="/v1", tags=["orders"])


def _order_item_response(item: OrderItem) -> OrderItemResponse:
    return OrderItemResponse(
        listing_id=item.listing_id,
        listing_title=item.listing.title,
        listing_sku=item.listing.sku,
        quantity=item.quantity,
        unit_price_cents=item.unit_price_cents,
    )


def _order_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        buyer_ref=order.buyer_ref,
        status=order.status,
        total_cents=order.total_cents,
        currency=order.currency,
        placed_at=order.placed_at,
        delivered_at=order.delivered_at,
        updated_at=order.updated_at,
        items=[_order_item_response(item) for item in order.items],
    )


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    seller_id: uuid.UUID = Depends(require_seller),
    session: AsyncSession = Depends(get_db_session),
    status: OrderStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> OrderListResponse:
    stmt = (
        select(Order)
        .where(Order.seller_id == seller_id)
        .options(selectinload(Order.items).selectinload(OrderItem.listing))
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if cursor:
        cursor_placed_at, cursor_id = decode_orders_cursor(cursor)
        stmt = stmt.where(tuple_(Order.placed_at, Order.id) < tuple_(cursor_placed_at, cursor_id))
    stmt = stmt.order_by(Order.placed_at.desc(), Order.id.desc()).limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = (
        encode_orders_cursor(page_rows[-1].placed_at, page_rows[-1].id) if has_more else None
    )
    return OrderListResponse(
        items=[_order_response(order) for order in page_rows], next_cursor=next_cursor
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: uuid.UUID,
    seller_id: uuid.UUID = Depends(require_seller),
    session: AsyncSession = Depends(get_db_session),
) -> OrderResponse:
    stmt = (
        select(Order)
        .where(Order.id == order_id, Order.seller_id == seller_id)
        .options(selectinload(Order.items).selectinload(OrderItem.listing))
    )
    order = (await session.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise not_found("Order not found.")
    return _order_response(order)


@router.post(
    "/orders/{order_id}/refund-requests", response_model=SupportCaseResponse, status_code=201
)
async def create_refund_request(
    order_id: uuid.UUID,
    body: RefundRequestBody,
    seller_id: uuid.UUID = Depends(require_seller),
    session: AsyncSession = Depends(get_db_session),
) -> SupportCaseResponse:
    try:
        case = await request_refund(session, seller_id, order_id, body.reason)
    except OrderNotFound as exc:
        raise not_found("Order not found.") from exc
    except AlreadyRequested as exc:
        raise conflict("A refund request is already open for this order.") from exc
    except NotEligible as exc:
        raise unprocessable(exc.reason) from exc
    return SupportCaseResponse.model_validate(case)
