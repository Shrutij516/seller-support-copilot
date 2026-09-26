import uuid
from collections import defaultdict

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import CaseStatus, CaseType, Order, OrderStatus, SupportCase
from copilot_api.scripts.seed import seed_data

pytestmark = pytest.mark.integration

_NO_CASE_STATUSES = (
    OrderStatus.PENDING,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
    OrderStatus.CANCELLED,
)


async def test_seeded_refund_requested_and_refunded_orders_have_matching_cases(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_data(session)

    async with session_factory() as verify:
        orders = (await verify.execute(select(Order))).scalars().all()
        cases = (await verify.execute(select(SupportCase))).scalars().all()

    cases_by_order: dict[uuid.UUID, list[SupportCase]] = defaultdict(list)
    for case in cases:
        if case.order_id is not None:
            cases_by_order[case.order_id].append(case)

    refund_requested = [o for o in orders if o.status == OrderStatus.REFUND_REQUESTED]
    refunded = [o for o in orders if o.status == OrderStatus.REFUNDED]
    # Sanity: the fixed seed actually produces both, or this test would pass vacuously.
    assert refund_requested
    assert refunded

    for order in refund_requested:
        order_cases = cases_by_order[order.id]
        assert len(order_cases) == 1, f"order {order.id} has {len(order_cases)} cases, want 1"
        assert order_cases[0].type == CaseType.REFUND_REQUEST
        assert order_cases[0].status == CaseStatus.OPEN

    for order in refunded:
        order_cases = cases_by_order[order.id]
        assert len(order_cases) == 1, f"order {order.id} has {len(order_cases)} cases, want 1"
        assert order_cases[0].type == CaseType.REFUND_REQUEST
        assert order_cases[0].status == CaseStatus.RESOLVED

    for order in orders:
        if order.status in _NO_CASE_STATUSES:
            assert order.id not in cases_by_order
