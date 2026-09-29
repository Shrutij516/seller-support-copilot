from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import OrderStatus
from tests.integration.conftest import mint_token
from tests.integration.factories import (
    create_listing,
    create_order,
    create_order_item,
    create_seller,
)

pytestmark = pytest.mark.integration


async def test_get_order_not_owned_is_404(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        owner = await create_seller(session, cognito_sub="sub-owner")
        await create_seller(session, cognito_sub="sub-other")
        order = await create_order(
            session,
            owner.id,
            status=OrderStatus.DELIVERED,
            delivered_at=datetime.now(UTC) - timedelta(days=1),
        )

    token = mint_token(rsa_keypair, sub="sub-other", groups=["seller"])
    response = api_client.get(
        f"/v1/orders/{order.id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


async def test_get_order_not_found_is_404(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        await create_seller(session, cognito_sub="sub-solo")

    token = mint_token(rsa_keypair, sub="sub-solo", groups=["seller"])
    response = api_client.get(
        "/v1/orders/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_get_own_order_returns_items(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-own-order")
        order = await create_order(session, seller.id, status=OrderStatus.SHIPPED)

    token = mint_token(rsa_keypair, sub="sub-own-order", groups=["seller"])
    response = api_client.get(
        f"/v1/orders/{order.id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(order.id)
    assert body["status"] == "shipped"
    assert body["items"] == []


async def test_get_order_items_include_listing_title_and_sku(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-order-items")
        listing = await create_listing(
            session, seller.id, title="Wireless Mouse", sku="SKU-MOUSE01", price_cents=2599
        )
        order = await create_order(session, seller.id, status=OrderStatus.SHIPPED)
        await create_order_item(session, order.id, listing.id, quantity=2, unit_price_cents=2599)

    token = mint_token(rsa_keypair, sub="sub-order-items", groups=["seller"])
    response = api_client.get(
        f"/v1/orders/{order.id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["listing_title"] == "Wireless Mouse"
    assert items[0]["listing_sku"] == "SKU-MOUSE01"
    assert items[0]["quantity"] == 2
    assert items[0]["unit_price_cents"] == 2599


async def test_list_orders_items_include_listing_title_and_sku(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-list-order-items")
        listing = await create_listing(
            session, seller.id, title="Ceramic Mug", sku="SKU-MUG01", price_cents=1299
        )
        order = await create_order(session, seller.id, status=OrderStatus.SHIPPED)
        await create_order_item(session, order.id, listing.id, unit_price_cents=1299)

    token = mint_token(rsa_keypair, sub="sub-list-order-items", groups=["seller"])
    response = api_client.get("/v1/orders", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    items = response.json()["items"][0]["items"]
    assert items[0]["listing_title"] == "Ceramic Mug"
    assert items[0]["listing_sku"] == "SKU-MUG01"


# --- refund-requests: 201 / 409 / 422 ---


async def test_refund_request_success_is_201(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-refund-ok")
        order = await create_order(
            session,
            seller.id,
            status=OrderStatus.DELIVERED,
            delivered_at=datetime.now(UTC) - timedelta(days=1),
        )

    token = mint_token(rsa_keypair, sub="sub-refund-ok", groups=["seller"])
    response = api_client.post(
        f"/v1/orders/{order.id}/refund-requests",
        json={"reason": "the item arrived broken in transit"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["order_id"] == str(order.id)
    assert body["status"] == "open"
    assert body["type"] == "refund_request"


async def test_refund_request_already_open_is_409(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-refund-409")
        order = await create_order(
            session,
            seller.id,
            status=OrderStatus.DELIVERED,
            delivered_at=datetime.now(UTC) - timedelta(days=1),
        )

    token = mint_token(rsa_keypair, sub="sub-refund-409", groups=["seller"])
    first = api_client.post(
        f"/v1/orders/{order.id}/refund-requests",
        json={"reason": "the item arrived broken in transit"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 201

    second = api_client.post(
        f"/v1/orders/{order.id}/refund-requests",
        json={"reason": "asking again about the same order"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409


async def test_refund_request_not_eligible_is_422(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-refund-422")
        order = await create_order(session, seller.id, status=OrderStatus.SHIPPED)

    token = mint_token(rsa_keypair, sub="sub-refund-422", groups=["seller"])
    response = api_client.post(
        f"/v1/orders/{order.id}/refund-requests",
        json={"reason": "the item hasn't even arrived yet"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# --- pagination: no duplicates or gaps across pages ---


async def test_orders_pagination_has_no_duplicates_or_gaps(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-pagination")
        now = datetime.now(UTC)
        created_ids = set()
        for i in range(25):
            order = await create_order(
                session, seller.id, status=OrderStatus.PENDING, placed_at=now - timedelta(minutes=i)
            )
            created_ids.add(str(order.id))

    token = mint_token(rsa_keypair, sub="sub-pagination", groups=["seller"])
    headers = {"Authorization": f"Bearer {token}"}

    seen_ids: list[str] = []
    cursor = None
    for _ in range(10):  # safety cap so a pagination bug can't loop forever
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor
        response = api_client.get("/v1/orders", params=params, headers=headers)
        assert response.status_code == 200
        body = response.json()
        seen_ids.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(seen_ids) == len(created_ids), "pagination lost or duplicated rows"
    assert len(seen_ids) == len(set(seen_ids)), "pagination returned a duplicate"
    assert set(seen_ids) == created_ids, "pagination has a gap"
