"""Plain helper functions for building fixture rows. Not fixtures themselves: call with an
open session from the `session_factory` fixture, inside `session.begin()`.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.models import CaseStatus, CaseType, Order, OrderStatus, Seller, SupportCase


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
    order = Order(
        id=uuid.uuid4(),
        seller_id=seller_id,
        buyer_ref=f"BUYER-{uuid.uuid4().hex[:8]}",
        status=status,
        total_cents=1000,
        currency="USD",
        placed_at=placed_at or datetime.now(UTC),
        delivered_at=delivered_at,
    )
    session.add(order)
    await session.flush()
    return order


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
