import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.conftest import mint_token
from tests.integration.factories import create_seller

pytestmark = pytest.mark.integration


async def _seller_token(
    session_factory: async_sessionmaker[AsyncSession], rsa_keypair: RSAPrivateKey, sub: str
) -> str:
    async with session_factory() as session, session.begin():
        await create_seller(session, cognito_sub=sub)
    return mint_token(rsa_keypair, sub=sub, groups=["seller"])


async def test_refund_request_extra_field_is_422(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    token = await _seller_token(session_factory, rsa_keypair, "sub-val-extra")
    response = api_client.post(
        "/v1/orders/00000000-0000-0000-0000-000000000000/refund-requests",
        json={"reason": "a perfectly good reason here", "not_a_real_field": "sneaky"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_refund_request_short_reason_is_422(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    token = await _seller_token(session_factory, rsa_keypair, "sub-val-short")
    response = api_client.post(
        "/v1/orders/00000000-0000-0000-0000-000000000000/refund-requests",
        json={"reason": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_get_order_bad_uuid_is_422(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    token = await _seller_token(session_factory, rsa_keypair, "sub-val-uuid")
    response = api_client.get(
        "/v1/orders/not-a-valid-uuid", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422


async def test_orders_limit_out_of_range_is_422(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    token = await _seller_token(session_factory, rsa_keypair, "sub-val-limit")

    too_high = api_client.get(
        "/v1/orders", params={"limit": 101}, headers={"Authorization": f"Bearer {token}"}
    )
    assert too_high.status_code == 422

    too_low = api_client.get(
        "/v1/orders", params={"limit": 0}, headers={"Authorization": f"Bearer {token}"}
    )
    assert too_low.status_code == 422


async def test_chat_session_extra_field_is_422(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    token = await _seller_token(session_factory, rsa_keypair, "sub-val-chat")
    response = api_client.post(
        "/v1/chat/sessions",
        json={"title": "A question", "unexpected": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
