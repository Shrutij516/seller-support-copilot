import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import CaseStatus
from tests.integration.conftest import mint_token
from tests.integration.factories import create_case, create_seller

pytestmark = pytest.mark.integration


async def test_seller_calling_admin_route_is_403(
    api_client: TestClient, rsa_keypair: RSAPrivateKey
) -> None:
    token = mint_token(rsa_keypair, sub="sub-not-admin", groups=["seller"])
    response = api_client.get("/v1/admin/cases", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"


async def test_seller_calling_admin_patch_is_403(
    api_client: TestClient, rsa_keypair: RSAPrivateKey
) -> None:
    token = mint_token(rsa_keypair, sub="sub-not-admin-2", groups=["seller"])
    response = api_client.patch(
        "/v1/admin/cases/00000000-0000-0000-0000-000000000000",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_admin_list_cases_success(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        await create_case(session, seller.id, None, status=CaseStatus.OPEN)

    token = mint_token(rsa_keypair, sub="sub-admin-1", groups=["admin"])
    response = api_client.get("/v1/admin/cases", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1


async def test_admin_case_transition_open_to_in_progress_is_valid(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        case = await create_case(session, seller.id, None, status=CaseStatus.OPEN)

    token = mint_token(rsa_keypair, sub="sub-admin-2", groups=["admin"])
    response = api_client.patch(
        f"/v1/admin/cases/{case.id}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


async def test_admin_case_transition_open_to_resolved_is_invalid(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    """Skipping a step (open -> resolved, bypassing in_progress) is rejected, not allowed."""
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        case = await create_case(session, seller.id, None, status=CaseStatus.OPEN)

    token = mint_token(rsa_keypair, sub="sub-admin-3", groups=["admin"])
    response = api_client.patch(
        f"/v1/admin/cases/{case.id}",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


async def test_admin_case_transition_from_resolved_is_invalid(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    """resolved is terminal: no transition out of it is allowed."""
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        case = await create_case(session, seller.id, None, status=CaseStatus.RESOLVED)

    token = mint_token(rsa_keypair, sub="sub-admin-4", groups=["admin"])
    response = api_client.patch(
        f"/v1/admin/cases/{case.id}",
        json={"status": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
