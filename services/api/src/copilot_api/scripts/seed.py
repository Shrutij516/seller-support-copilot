"""Deterministic synthetic data for local development. Run via `make seed`.

Fixed Faker/random seed so re-running gives the same data (useful for demos and for writing
tests/queries against predictable rows). Refuses to run against APP_ENV=prod.
"""

import random
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.config import get_settings
from copilot_api.db import create_engine, create_session_factory
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
from copilot_api.services.refunds import REFUND_WINDOW_DAYS

SEED = 1234
NUM_SELLERS = 20
NUM_ORDERS = 500
MIN_LISTINGS_PER_SELLER = 3
MAX_LISTINGS_PER_SELLER = 6
# Guaranteed per seller, on top of the randomly distributed orders below, so every seller has
# both refund-eligible and refund-ineligible delivered orders to test against instead of that
# being left to chance (a seller could otherwise end up with zero of one kind).
GUARANTEED_DELIVERED_IN_WINDOW_PER_SELLER = 3
GUARANTEED_DELIVERED_OUTSIDE_WINDOW_PER_SELLER = 2

# Order status mix: mostly delivered, with a realistic spread of everything else.
ORDER_STATUS_WEIGHTS: dict[OrderStatus, int] = {
    OrderStatus.DELIVERED: 45,
    OrderStatus.SHIPPED: 15,
    OrderStatus.PENDING: 10,
    OrderStatus.CANCELLED: 10,
    OrderStatus.REFUND_REQUESTED: 8,
    OrderStatus.REFUNDED: 12,
}
DELIVERED_STATUSES = (OrderStatus.DELIVERED, OrderStatus.REFUND_REQUESTED, OrderStatus.REFUNDED)
# status -> the support_case status a seeded order in that status implies.
CASE_STATUS_FOR_ORDER_STATUS: dict[OrderStatus, CaseStatus] = {
    OrderStatus.REFUND_REQUESTED: CaseStatus.OPEN,
    OrderStatus.REFUNDED: CaseStatus.RESOLVED,
}

# Real seller-support phrasing, not lorem/fake.sentence() word salad. Reused across many
# orders is fine and realistic: real support queues have repeat complaint categories.
REFUND_CASE_DESCRIPTIONS = [
    "The item arrived damaged during shipping.",
    "Buyer says the product doesn't match the listing description.",
    "Wrong item was shipped to the buyer.",
    "Buyer received the item too late and no longer needs it.",
    "Item was defective on arrival; buyer is requesting a refund.",
    "Buyer changed their mind and would like to return the item.",
    "Package arrived opened and missing parts.",
    "Buyer reports the item stopped working after a few days.",
    "Duplicate order was placed by mistake.",
    "Buyer says the size or color received was incorrect.",
    "Item was never delivered according to the buyer.",
    "Buyer found a better price elsewhere and wants to cancel.",
]


def _make_sellers(fake: Faker, rng: random.Random) -> list[Seller]:
    return [
        Seller(email=fake.unique.company_email(), display_name=fake.company())
        for _ in range(NUM_SELLERS)
    ]


def _make_listings(fake: Faker, rng: random.Random, sellers: list[Seller]) -> list[Listing]:
    # Every seller gets several listings at varied prices, not left to chance: a seller
    # `rng.choice` never picks would otherwise end up with none, and one that's picked rarely
    # could end up with just one, making every order look identical.
    listings = []
    for seller in sellers:
        count = rng.randint(MIN_LISTINGS_PER_SELLER, MAX_LISTINGS_PER_SELLER)
        for _ in range(count):
            status = rng.choices(
                [ListingStatus.ACTIVE, ListingStatus.INACTIVE, ListingStatus.SUPPRESSED],
                weights=[80, 15, 5],
            )[0]
            listings.append(
                Listing(
                    seller_id=seller.id,
                    sku=fake.unique.bothify("SKU-########"),
                    title=fake.catch_phrase(),
                    price_cents=rng.randint(500, 20000),
                    status=status,
                )
            )
    return listings


def _placed_and_delivered(
    rng: random.Random,
    now: datetime,
    status: OrderStatus,
    *,
    inside_window: bool | None = None,
) -> tuple[datetime, datetime | None]:
    """placed_at is always <= delivered_at (when there is one) <= now: delivered_at is chosen
    first, then placed_at is backdated from it by a plausible shipping gap, instead of picking
    both independently (the previous bug: two independent random offsets from `now` had no
    guaranteed relationship, so delivered_at randomly landed before placed_at).

    `inside_window` forces delivered_at inside/outside the REFUND_WINDOW_DAYS window; None
    (the default, used for the randomly distributed orders) lets a coin flip decide.
    """
    if status not in DELIVERED_STATUSES:
        return now - timedelta(days=rng.randint(1, 120)), None

    if inside_window is None:
        inside_window = rng.random() < 0.5

    if inside_window:
        delivered_at = now - timedelta(days=rng.randint(0, REFUND_WINDOW_DAYS - 1))
    else:
        delivered_at = now - timedelta(days=rng.randint(REFUND_WINDOW_DAYS + 1, 120))

    placed_at = delivered_at - timedelta(days=rng.randint(0, 14))
    return placed_at, delivered_at


def _make_order(
    fake: Faker,
    rng: random.Random,
    seller: Seller,
    seller_listings: list[Listing],
    status: OrderStatus,
    now: datetime,
    *,
    inside_window: bool | None = None,
) -> tuple[Order, list[OrderItem]]:
    placed_at, delivered_at = _placed_and_delivered(rng, now, status, inside_window=inside_window)
    order = Order(
        id=uuid.uuid4(),
        seller_id=seller.id,
        buyer_ref=fake.unique.bothify("BUYER-########"),
        status=status,
        total_cents=0,
        currency="USD",
        placed_at=placed_at,
        delivered_at=delivered_at,
    )

    chosen = rng.sample(seller_listings, k=min(rng.randint(1, 3), len(seller_listings)))
    items: list[OrderItem] = []
    total_cents = 0
    for listing in chosen:
        quantity = rng.randint(1, 3)
        items.append(
            OrderItem(
                order_id=order.id,
                listing_id=listing.id,
                quantity=quantity,
                unit_price_cents=listing.price_cents,
            )
        )
        total_cents += quantity * listing.price_cents
    order.total_cents = total_cents
    return order, items


def _make_orders_and_items(
    fake: Faker,
    rng: random.Random,
    sellers: list[Seller],
    listings: list[Listing],
) -> tuple[list[Order], list[OrderItem]]:
    listings_by_seller: dict[uuid.UUID, list[Listing]] = defaultdict(list)
    for listing in listings:
        listings_by_seller[listing.seller_id].append(listing)
    sellers_with_listings = [s for s in sellers if listings_by_seller[s.id]]

    now = datetime.now(UTC)
    orders: list[Order] = []
    items: list[OrderItem] = []

    # Guaranteed orders first, so the invariant holds regardless of how the random draw below
    # happens to land.
    for seller in sellers_with_listings:
        seller_listings = listings_by_seller[seller.id]
        for _ in range(GUARANTEED_DELIVERED_IN_WINDOW_PER_SELLER):
            order, order_items = _make_order(
                fake, rng, seller, seller_listings, OrderStatus.DELIVERED, now, inside_window=True
            )
            orders.append(order)
            items.extend(order_items)
        for _ in range(GUARANTEED_DELIVERED_OUTSIDE_WINDOW_PER_SELLER):
            order, order_items = _make_order(
                fake, rng, seller, seller_listings, OrderStatus.DELIVERED, now, inside_window=False
            )
            orders.append(order)
            items.extend(order_items)

    statuses = list(ORDER_STATUS_WEIGHTS)
    weights = list(ORDER_STATUS_WEIGHTS.values())
    for _ in range(max(0, NUM_ORDERS - len(orders))):
        seller = rng.choice(sellers_with_listings)
        seller_listings = listings_by_seller[seller.id]
        status = rng.choices(statuses, weights=weights)[0]
        order, order_items = _make_order(fake, rng, seller, seller_listings, status, now)
        orders.append(order)
        items.extend(order_items)

    return orders, items


def _make_support_cases(rng: random.Random, orders: list[Order]) -> list[SupportCase]:
    """One support_case per refund_requested/refunded order, so the seeded data satisfies
    the same invariant the app maintains: refund_requested -> exactly one open refund_request
    case; refunded -> exactly one resolved one.
    """
    cases = []
    for order in orders:
        case_status = CASE_STATUS_FOR_ORDER_STATUS.get(order.status)
        if case_status is None:
            continue
        cases.append(
            SupportCase(
                seller_id=order.seller_id,
                order_id=order.id,
                type=CaseType.REFUND_REQUEST,
                status=case_status,
                description=rng.choice(REFUND_CASE_DESCRIPTIONS),
            )
        )
    return cases


async def seed_data(session: AsyncSession) -> dict[str, int]:
    """The actual data generation, given an open session. Testable independent of settings,
    engine creation, or the APP_ENV guard.
    """
    Faker.seed(SEED)
    fake = Faker()
    rng = random.Random(SEED)

    sellers = _make_sellers(fake, rng)
    session.add_all(sellers)
    await session.flush()

    listings = _make_listings(fake, rng, sellers)
    session.add_all(listings)
    await session.flush()

    orders, items = _make_orders_and_items(fake, rng, sellers, listings)
    session.add_all(orders)
    session.add_all(items)
    await session.flush()

    cases = _make_support_cases(rng, orders)
    session.add_all(cases)
    await session.flush()

    return {
        "sellers": len(sellers),
        "listings": len(listings),
        "orders": len(orders),
        "order_items": len(items),
        "support_cases": len(cases),
    }


async def seed() -> dict[str, int]:
    settings = get_settings()
    if settings.app_env == "prod":
        print("Refusing to seed: APP_ENV=prod", file=sys.stderr)
        raise SystemExit(1)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            return await seed_data(session)
    finally:
        await engine.dispose()


def main() -> None:
    import asyncio

    counts = asyncio.run(seed())
    print(counts)


if __name__ == "__main__":
    main()
