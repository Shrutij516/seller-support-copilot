from datetime import UTC, datetime, timedelta

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


# --- default ordering: open, then in_progress, then resolved; oldest first within each ---


async def test_admin_list_cases_default_order_is_open_then_in_progress_then_resolved(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        # Insert in an order that a naive created_at-only sort would NOT fix: newest
        # resolved case first, oldest open case last, so this only passes if status is
        # actually the primary sort key.
        resolved = await create_case(
            session, seller.id, None, status=CaseStatus.RESOLVED, created_at=now
        )
        in_progress = await create_case(
            session,
            seller.id,
            None,
            status=CaseStatus.IN_PROGRESS,
            created_at=now - timedelta(hours=1),
        )
        open_new = await create_case(
            session,
            seller.id,
            None,
            status=CaseStatus.OPEN,
            created_at=now - timedelta(hours=2),
        )
        open_old = await create_case(
            session,
            seller.id,
            None,
            status=CaseStatus.OPEN,
            created_at=now - timedelta(hours=3),
        )

    token = mint_token(rsa_keypair, sub="sub-admin-order", groups=["admin"])
    response = api_client.get(
        "/v1/admin/cases", params={"limit": 100}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    # open (oldest first), then in_progress, then resolved.
    expected_order = [str(open_old.id), str(open_new.id), str(in_progress.id), str(resolved.id)]
    assert [i for i in ids if i in expected_order] == expected_order


async def test_admin_list_cases_ties_broken_by_id(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    """Same status, same created_at: id is the final tiebreaker, so the order is strict
    (not just stable-by-luck) and keyset pagination has something unique to seek from.
    """
    same_instant = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        cases = [
            await create_case(
                session, seller.id, None, status=CaseStatus.OPEN, created_at=same_instant
            )
            for _ in range(5)
        ]
    expected_ids = sorted(str(c.id) for c in cases)

    token = mint_token(rsa_keypair, sub="sub-admin-ties", groups=["admin"])
    response = api_client.get(
        "/v1/admin/cases",
        params={"status": "open", "limit": 100},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"] if item["id"] in expected_ids]
    assert ids == expected_ids


async def test_admin_list_cases_pagination_has_no_duplicates_or_gaps_with_ties(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    same_instant = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        created_ids = set()
        for _ in range(25):
            # Every row shares the exact same status and created_at: pagination must still
            # be correct, breaking ties by id alone.
            case = await create_case(
                session, seller.id, None, status=CaseStatus.OPEN, created_at=same_instant
            )
            created_ids.add(str(case.id))

    token = mint_token(rsa_keypair, sub="sub-admin-pagination", groups=["admin"])
    headers = {"Authorization": f"Bearer {token}"}

    seen_ids: list[str] = []
    cursor = None
    for _ in range(10):  # safety cap so a pagination bug can't loop forever
        params: dict[str, str | int] = {"status": "open", "limit": 10}
        if cursor:
            params["cursor"] = cursor
        response = api_client.get("/v1/admin/cases", params=params, headers=headers)
        assert response.status_code == 200
        body = response.json()
        seen_ids.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(seen_ids) == len(created_ids), "pagination lost or duplicated rows"
    assert len(seen_ids) == len(set(seen_ids)), "pagination returned a duplicate"
    assert set(seen_ids) == created_ids, "pagination has a gap"


async def test_admin_list_cases_includes_seller_display_name(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        seller.display_name = "Acme Widgets"
        await create_case(session, seller.id, None, status=CaseStatus.OPEN)

    token = mint_token(rsa_keypair, sub="sub-admin-seller-name", groups=["admin"])
    response = api_client.get("/v1/admin/cases", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert any(item["seller_display_name"] == "Acme Widgets" for item in response.json()["items"])


async def test_admin_update_case_response_includes_seller_display_name(
    api_client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session)
        seller.display_name = "Beta Corp"
        case = await create_case(session, seller.id, None, status=CaseStatus.OPEN)

    token = mint_token(rsa_keypair, sub="sub-admin-patch-name", groups=["admin"])
    response = api_client.patch(
        f"/v1/admin/cases/{case.id}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["seller_display_name"] == "Beta Corp"
