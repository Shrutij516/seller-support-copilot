"""The 401 matrix (priority per spec) plus /v1/me happy path, proving the whole auth chain
(JWKS verification, iss/exp/token_use/client_id checks, cognito:groups -> roles, sub ->
seller_id) works end to end against locally minted tokens.
"""

from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import Seller
from tests.integration.conftest import TEST_CLIENT_ID, TEST_ISSUER, TEST_KID, mint_token

pytestmark = pytest.mark.integration


async def _create_seller(
    session_factory: async_sessionmaker[AsyncSession], *, cognito_sub: str
) -> Seller:
    async with session_factory() as session:
        seller = Seller(
            email=f"{cognito_sub}@example.com", display_name="Test Seller", cognito_sub=cognito_sub
        )
        session.add(seller)
        await session.commit()
        await session.refresh(seller)
        return seller


async def test_me_with_valid_token_returns_seller_profile(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    seller = await _create_seller(session_factory, cognito_sub="sub-me-1")
    token = mint_token(rsa_keypair, sub="sub-me-1", groups=["seller"])

    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["seller_id"] == str(seller.id)
    assert body["email"] == seller.email
    assert body["roles"] == ["seller"]


async def test_me_admin_returns_200_with_null_seller(
    api_client: TestClient, rsa_keypair: RSAPrivateKey
) -> None:
    # No sellers row at all for this sub: an admin isn't necessarily also a seller.
    token = mint_token(rsa_keypair, sub="sub-admin-no-seller-row", groups=["admin"])

    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["admin"]
    assert body["seller_id"] is None
    assert body["email"] is None
    assert body["display_name"] is None


async def test_me_seller_not_provisioned_is_403(
    api_client: TestClient, rsa_keypair: RSAPrivateKey
) -> None:
    # cognito:groups says "seller", but no sellers row has this sub yet.
    token = mint_token(rsa_keypair, sub="sub-seller-not-provisioned", groups=["seller"])

    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "account not provisioned"


async def test_no_token_is_401(api_client: TestClient) -> None:
    response = api_client.get("/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


async def test_expired_token_is_401(api_client: TestClient, rsa_keypair: RSAPrivateKey) -> None:
    token = mint_token(rsa_keypair, groups=["seller"], expires_in=timedelta(seconds=-60))
    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_wrong_issuer_is_401(api_client: TestClient, rsa_keypair: RSAPrivateKey) -> None:
    token = mint_token(rsa_keypair, groups=["seller"], issuer="https://not-our-pool.example.com")
    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_wrong_client_id_is_401(api_client: TestClient, rsa_keypair: RSAPrivateKey) -> None:
    token = mint_token(rsa_keypair, groups=["seller"], client_id="some-other-app-client")
    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_bad_signature_is_401(
    api_client: TestClient, other_rsa_keypair: RSAPrivateKey
) -> None:
    # Signed with a key that isn't in the JWKS at all: the kid still matches (same kid
    # value), but the signature can't verify against the real public key.
    token = mint_token(
        other_rsa_keypair, groups=["seller"], kid=TEST_KID, signing_key=other_rsa_keypair
    )
    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_unknown_kid_is_401(api_client: TestClient, rsa_keypair: RSAPrivateKey) -> None:
    token = mint_token(rsa_keypair, groups=["seller"], kid="a-kid-not-in-our-jwks")
    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_id_token_instead_of_access_token_is_401(
    api_client: TestClient, rsa_keypair: RSAPrivateKey
) -> None:
    token = mint_token(rsa_keypair, groups=["seller"], token_use="id")
    response = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_malformed_bearer_header_is_401(api_client: TestClient) -> None:
    response = api_client.get("/v1/me", headers={"Authorization": "not-a-bearer-token"})
    assert response.status_code == 401


def test_issuer_and_client_id_fixture_constants_are_distinct_from_real_aws() -> None:
    # Sanity check the test fixtures aren't accidentally pointed at something real.
    assert "TESTPOOL" in TEST_ISSUER
    assert TEST_CLIENT_ID.startswith("test-")
