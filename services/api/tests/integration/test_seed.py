import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import (
    CaseStatus,
    CaseType,
    Listing,
    Order,
    OrderStatus,
    Seller,
    SupportCase,
)
from copilot_api.scripts.seed import (
    GUARANTEED_DELIVERED_IN_WINDOW_PER_SELLER,
    GUARANTEED_DELIVERED_OUTSIDE_WINDOW_PER_SELLER,
    MIN_LISTINGS_PER_SELLER,
    seed_data,
)
from copilot_api.services.refunds import REFUND_WINDOW_DAYS

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


async def test_seeded_orders_never_have_delivered_at_before_placed_at(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_data(session)

    async with session_factory() as verify:
        orders = (await verify.execute(select(Order))).scalars().all()

    delivered = [o for o in orders if o.delivered_at is not None]
    assert delivered  # sanity: the fixed seed actually produces some, or this is vacuous
    for order in delivered:
        assert order.delivered_at is not None
        assert order.delivered_at >= order.placed_at, (
            f"order {order.id}: delivered_at {order.delivered_at} is before "
            f"placed_at {order.placed_at}"
        )


async def test_seeded_listings_are_varied_per_seller(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_data(session)

    async with session_factory() as verify:
        sellers = (await verify.execute(select(Seller))).scalars().all()
        listings = (await verify.execute(select(Listing))).scalars().all()

    listings_by_seller: dict[uuid.UUID, list[Listing]] = defaultdict(list)
    for listing in listings:
        listings_by_seller[listing.seller_id].append(listing)

    for seller in sellers:
        seller_listings = listings_by_seller[seller.id]
        assert len(seller_listings) >= MIN_LISTINGS_PER_SELLER, (
            f"seller {seller.id} has only {len(seller_listings)} listings"
        )
        prices = {listing.price_cents for listing in seller_listings}
        assert len(prices) > 1, f"seller {seller.id}'s listings are all the same price"


async def test_seeded_sellers_have_delivered_orders_inside_and_outside_refund_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_data(session)

    async with session_factory() as verify:
        sellers = (await verify.execute(select(Seller))).scalars().all()
        orders = (await verify.execute(select(Order))).scalars().all()

    now = datetime.now(UTC)
    window_cutoff = now - timedelta(days=REFUND_WINDOW_DAYS)
    orders_by_seller: dict[uuid.UUID, list[Order]] = defaultdict(list)
    for order in orders:
        orders_by_seller[order.seller_id].append(order)

    for seller in sellers:
        seller_orders = [
            o for o in orders_by_seller[seller.id] if o.status == OrderStatus.DELIVERED
        ]
        in_window = [o for o in seller_orders if o.delivered_at and o.delivered_at >= window_cutoff]
        outside_window = [
            o for o in seller_orders if o.delivered_at and o.delivered_at < window_cutoff
        ]
        assert len(in_window) >= GUARANTEED_DELIVERED_IN_WINDOW_PER_SELLER, (
            f"seller {seller.id} has only {len(in_window)} delivered orders inside the "
            "refund window"
        )
        assert len(outside_window) >= GUARANTEED_DELIVERED_OUTSIDE_WINDOW_PER_SELLER, (
            f"seller {seller.id} has only {len(outside_window)} delivered orders outside the "
            "refund window"
        )


async def test_seeded_case_descriptions_are_not_lorem_text(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_data(session)

    async with session_factory() as verify:
        cases = (await verify.execute(select(SupportCase))).scalars().all()

    assert cases
    # fake.sentence() (the old, rejected approach) strings together short unrelated common
    # words; real support phrasing reliably contains at least one of these domain terms.
    domain_terms = ("buyer", "item", "order", "refund", "delivered", "shipped", "package")
    for case in cases:
        lowered = case.description.lower()
        assert any(term in lowered for term in domain_terms), (
            f"case {case.id} description doesn't read like real support text: {case.description!r}"
        )
