"""get_db_session itself, driven directly as the async generator FastAPI treats it as
(__anext__/athrow), not through the API. Every API test overrides this dependency (it has
to, to redirect to the isolated test database), so nothing else exercises its actual
commit/rollback logic against the real function.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import cast

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.deps import get_db_session
from copilot_api.models import Seller

pytestmark = pytest.mark.integration


def _fake_request(session_factory: async_sessionmaker[AsyncSession]) -> Request:
    state = type("State", (), {"db_session_factory": session_factory})()
    app = type("App", (), {"state": state})()
    request = type("Request", (), {"app": app})()
    return cast(Request, request)


def _as_generator(request: Request) -> AsyncGenerator[AsyncSession, None]:
    # get_db_session is typed as returning AsyncIterator (the FastAPI-facing contract), but
    # it's actually an async generator function; cast so athrow() type-checks here too.
    return cast("AsyncGenerator[AsyncSession, None]", get_db_session(request))


async def test_get_db_session_commits_on_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    request = _fake_request(session_factory)
    seller_id = uuid.uuid4()

    gen = _as_generator(request)
    session: AsyncSession = await anext(gen)
    session.add(Seller(id=seller_id, email=f"{seller_id}@example.com", display_name="Test"))
    await session.flush()
    with pytest.raises(StopAsyncIteration):
        await anext(gen)  # drives past `yield`, same as FastAPI does when the route returns

    async with session_factory() as verify:
        assert await verify.get(Seller, seller_id) is not None


async def test_get_db_session_rolls_back_on_exception(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    request = _fake_request(session_factory)
    seller_id = uuid.uuid4()

    gen = _as_generator(request)
    session: AsyncSession = await anext(gen)
    session.add(Seller(id=seller_id, email=f"{seller_id}@example.com", display_name="Test"))
    await session.flush()

    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("boom"))

    async with session_factory() as verify:
        assert await verify.get(Seller, seller_id) is None


async def test_get_db_session_rollback_reraises_original_exception(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FastAPI needs the original exception back (not swallowed) so its handler can still
    turn it into the right HTTP response.
    """
    request = _fake_request(session_factory)
    gen = _as_generator(request)
    await anext(gen)

    class BoomError(Exception):
        pass

    with pytest.raises(BoomError):
        await gen.athrow(BoomError("domain error"))
