from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import Order, OrderStatus
from tests.integration.factories import create_order, create_seller

pytestmark = pytest.mark.integration


async def test_delivered_at_before_placed_at_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)

    async with session_factory() as session:
        now = datetime.now(UTC)
        with pytest.raises(IntegrityError, match="ck_orders_delivered_at_after_placed_at"):
            await create_order(
                session,
                seller.id,
                status=OrderStatus.DELIVERED,
                placed_at=now,
                delivered_at=now - timedelta(days=1),
            )
        await session.rollback()


async def test_delivered_at_equal_to_placed_at_is_allowed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        now = datetime.now(UTC)
        order = await create_order(
            session, seller.id, status=OrderStatus.DELIVERED, placed_at=now, delivered_at=now
        )

    async with session_factory() as verify:
        refreshed = await verify.get(Order, order.id)
        assert refreshed is not None
        assert refreshed.delivered_at == refreshed.placed_at


async def test_null_delivered_at_is_allowed_regardless_of_placed_at(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        order = await create_order(
            session,
            seller.id,
            status=OrderStatus.PENDING,
            placed_at=datetime.now(UTC),
            delivered_at=None,
        )

    async with session_factory() as verify:
        refreshed = await verify.get(Order, order.id)
        assert refreshed is not None
        assert refreshed.delivered_at is None
