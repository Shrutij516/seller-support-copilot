import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import CaseStatus, Listing, ListingStatus
from tests.integration.conftest import mint_token
from tests.integration.factories import create_case, create_seller

pytestmark = pytest.mark.integration


async def test_list_listings_returns_only_own(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        mine = await create_seller(session, cognito_sub="sub-listings-mine")
        other = await create_seller(session, cognito_sub="sub-listings-other")
        session.add(
            Listing(
                seller_id=mine.id,
                sku="SKU-MINE-1",
                title="My widget",
                price_cents=1000,
                status=ListingStatus.ACTIVE,
            )
        )
        session.add(
            Listing(
                seller_id=other.id,
                sku="SKU-OTHER-1",
                title="Their widget",
                price_cents=2000,
                status=ListingStatus.ACTIVE,
            )
        )

    token = mint_token(rsa_keypair, sub="sub-listings-mine", groups=["seller"])
    response = api_client.get("/v1/listings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    skus = [item["sku"] for item in response.json()]
    assert skus == ["SKU-MINE-1"]


async def test_list_and_get_own_case(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, cognito_sub="sub-cases-1")
        case = await create_case(session, seller.id, None, status=CaseStatus.OPEN)

    token = mint_token(rsa_keypair, sub="sub-cases-1", groups=["seller"])
    headers = {"Authorization": f"Bearer {token}"}

    listed = api_client.get("/v1/cases", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == str(case.id) for item in listed.json()["items"])

    fetched = api_client.get(f"/v1/cases/{case.id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(case.id)


async def test_get_case_not_owned_is_404(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        owner = await create_seller(session, cognito_sub="sub-case-owner")
        await create_seller(session, cognito_sub="sub-case-other")
        case = await create_case(session, owner.id, None, status=CaseStatus.OPEN)

    token = mint_token(rsa_keypair, sub="sub-case-other", groups=["seller"])
    response = api_client.get(f"/v1/cases/{case.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


async def test_chat_session_create_list_and_messages(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        await create_seller(session, cognito_sub="sub-chat-1")

    token = mint_token(rsa_keypair, sub="sub-chat-1", groups=["seller"])
    headers = {"Authorization": f"Bearer {token}"}

    created = api_client.post(
        "/v1/chat/sessions", json={"title": "Where's my refund?"}, headers=headers
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    listed = api_client.get("/v1/chat/sessions", headers=headers)
    assert listed.status_code == 200
    assert any(s["session_id"] == session_id for s in listed.json()["items"])

    messages = api_client.get(f"/v1/chat/sessions/{session_id}/messages", headers=headers)
    assert messages.status_code == 200
    assert messages.json()["items"] == []


async def test_chat_messages_for_session_not_owned_is_404(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        await create_seller(session, cognito_sub="sub-chat-owner")
        await create_seller(session, cognito_sub="sub-chat-other")

    owner_token = mint_token(rsa_keypair, sub="sub-chat-owner", groups=["seller"])
    created = api_client.post(
        "/v1/chat/sessions",
        json={"title": "Private thread"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    other_token = mint_token(rsa_keypair, sub="sub-chat-other", groups=["seller"])
    response = api_client.get(
        f"/v1/chat/sessions/{session_id}/messages",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404
