"""Plain helper functions for building fixture rows. Not fixtures themselves: call with an
open session from the `session_factory` fixture, inside `session.begin()`.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.models import (
    CaseStatus,
    CaseType,
    Listing,
    ListingStatus,
    Order,
    OrderItem,
    OrderStatus,
    Seller,
    SupportCase,
)


@asynccontextmanager
async def unit_of_work(session: AsyncSession) -> AsyncIterator[None]:
    """Mirrors copilot_api.deps.get_db_session's commit/rollback contract, for tests that
    call a service function directly instead of going through the API: commits on success,
    rolls back and re-raises on any exception. Services never do this themselves.
    """
    try:
        yield
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def create_seller(
    session: AsyncSession, *, cognito_sub: str | None = None, email: str | None = None
) -> Seller:
    seller = Seller(
        email=email or f"{uuid.uuid4()}@example.com",
        display_name="Test Seller",
        cognito_sub=cognito_sub,
    )
    session.add(seller)
    await session.flush()
    return seller


async def create_order(
    session: AsyncSession,
    seller_id: uuid.UUID,
    *,
    status: OrderStatus = OrderStatus.DELIVERED,
    delivered_at: datetime | None = None,
    placed_at: datetime | None = None,
) -> Order:
    if placed_at is None:
        # Default placed_at relative to delivered_at (when given), not to "now": the two
        # must satisfy placed_at <= delivered_at (ck_orders_delivered_at_after_placed_at).
        placed_at = (
            delivered_at - timedelta(days=1) if delivered_at is not None else datetime.now(UTC)
        )
    order = Order(
        id=uuid.uuid4(),
        seller_id=seller_id,
        buyer_ref=f"BUYER-{uuid.uuid4().hex[:8]}",
        status=status,
        total_cents=1000,
        currency="USD",
        placed_at=placed_at,
        delivered_at=delivered_at,
    )
    session.add(order)
    await session.flush()
    return order


async def create_listing(
    session: AsyncSession,
    seller_id: uuid.UUID,
    *,
    title: str = "Test Listing",
    sku: str | None = None,
    price_cents: int = 1000,
    status: ListingStatus = ListingStatus.ACTIVE,
) -> Listing:
    listing = Listing(
        seller_id=seller_id,
        sku=sku or f"SKU-{uuid.uuid4().hex[:8].upper()}",
        title=title,
        price_cents=price_cents,
        status=status,
    )
    session.add(listing)
    await session.flush()
    return listing


async def create_order_item(
    session: AsyncSession,
    order_id: uuid.UUID,
    listing_id: uuid.UUID,
    *,
    quantity: int = 1,
    unit_price_cents: int = 1000,
) -> OrderItem:
    item = OrderItem(
        order_id=order_id,
        listing_id=listing_id,
        quantity=quantity,
        unit_price_cents=unit_price_cents,
    )
    session.add(item)
    await session.flush()
    return item


async def create_case(
    session: AsyncSession,
    seller_id: uuid.UUID,
    order_id: uuid.UUID | None,
    *,
    status: CaseStatus = CaseStatus.OPEN,
    case_type: CaseType = CaseType.REFUND_REQUEST,
    description: str = "test case",
) -> SupportCase:
    case = SupportCase(
        seller_id=seller_id,
        order_id=order_id,
        type=case_type,
        status=status,
        description=description,
    )
    session.add(case)
    await session.flush()
    return case
