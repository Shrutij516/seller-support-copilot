import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import Order, OrderStatus, Seller, SupportCase
from copilot_api.services.refunds import (
    REFUND_WINDOW_DAYS,
    AlreadyRequested,
    NotEligible,
    OrderNotFound,
    request_refund,
)

pytestmark = pytest.mark.integration

# `session_factory` comes from tests/integration/conftest.py: bound to the isolated
# `copilot_test` database, truncated after every test.


async def _make_seller(session: AsyncSession) -> Seller:
    seller = Seller(email=f"{uuid.uuid4()}@example.com", display_name="Test Seller")
    session.add(seller)
    await session.flush()
    return seller


async def _make_order(
    session: AsyncSession, seller: Seller, status: OrderStatus, delivered_at: datetime | None
) -> Order:
    order = Order(
        seller_id=seller.id,
        buyer_ref="buyer-1",
        status=status,
        total_cents=1000,
        currency="USD",
        placed_at=datetime.now(UTC) - timedelta(days=5),
        delivered_at=delivered_at,
    )
    session.add(order)
    await session.flush()
    return order


async def _case_count(
    session_factory: async_sessionmaker[AsyncSession], order_id: uuid.UUID
) -> int:
    async with session_factory() as session:
        result = await session.execute(select(SupportCase).where(SupportCase.order_id == order_id))
        return len(result.scalars().all())


async def test_request_refund_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seller = await _make_seller(session)
        order = await _make_order(
            session, seller, OrderStatus.DELIVERED, datetime.now(UTC) - timedelta(days=1)
        )
        await session.commit()

    async with session_factory() as session:
        case = await request_refund(session, seller.id, order.id, "wrong item")
        assert case.order_id == order.id

    async with session_factory() as verify:
        refreshed = await verify.get(Order, order.id)
        assert refreshed is not None
        assert refreshed.status == OrderStatus.REFUND_REQUESTED
    assert await _case_count(session_factory, order.id) == 1


async def test_request_refund_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seller = await _make_seller(session)
        other_seller = await _make_seller(session)
        order = await _make_order(
            session, seller, OrderStatus.DELIVERED, datetime.now(UTC) - timedelta(days=1)
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(OrderNotFound):
            await request_refund(session, other_seller.id, order.id, "not mine")


async def test_request_refund_ineligible_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seller = await _make_seller(session)
        order = await _make_order(session, seller, OrderStatus.SHIPPED, None)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(NotEligible):
            await request_refund(session, seller.id, order.id, "too early")


async def test_request_refund_outside_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seller = await _make_seller(session)
        order = await _make_order(
            session,
            seller,
            OrderStatus.DELIVERED,
            datetime.now(UTC) - timedelta(days=REFUND_WINDOW_DAYS + 5),
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(NotEligible):
            await request_refund(session, seller.id, order.id, "too late")


async def test_request_refund_already_requested(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seller = await _make_seller(session)
        order = await _make_order(
            session, seller, OrderStatus.DELIVERED, datetime.now(UTC) - timedelta(days=1)
        )
        await session.commit()

    async with session_factory() as session:
        await request_refund(session, seller.id, order.id, "first")

    async with session_factory() as session:
        with pytest.raises(AlreadyRequested):
            await request_refund(session, seller.id, order.id, "second")


async def test_request_refund_rolls_back_on_failure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seller = await _make_seller(session)
        order = await _make_order(
            session, seller, OrderStatus.DELIVERED, datetime.now(UTC) - timedelta(days=1)
        )
        await session.commit()

    async with session_factory() as session:
        with (
            mock.patch.object(session, "add", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            await request_refund(session, seller.id, order.id, "boom")

    async with session_factory() as verify:
        refreshed = await verify.get(Order, order.id)
        assert refreshed is not None
        assert refreshed.status == OrderStatus.DELIVERED
    assert await _case_count(session_factory, order.id) == 0


async def test_request_refund_concurrent_requests_exactly_one_succeeds(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seller = await _make_seller(session)
        order = await _make_order(
            session, seller, OrderStatus.DELIVERED, datetime.now(UTC) - timedelta(days=1)
        )
        await session.commit()

    async def attempt() -> SupportCase:
        async with session_factory() as session:
            return await request_refund(session, seller.id, order.id, "concurrent")

    results = await asyncio.gather(attempt(), attempt(), return_exceptions=True)
    successes = [r for r in results if isinstance(r, SupportCase)]
    failures = [r for r in results if isinstance(r, BaseException)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], AlreadyRequested)
    assert await _case_count(session_factory, order.id) == 1
