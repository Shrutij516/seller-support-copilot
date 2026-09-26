"""Shared FastAPI dependencies not specific to any one router."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One unit of work per request: every dependency and route handler that asks for a
    session in the same request gets this same one. Commits once the request completes
    without error; rolls back and re-raises if anything in the request raised, including a
    domain error (OrderNotFound, NotEligible, ...) that FastAPI will still turn into a 4xx.
    Services and route handlers never call session.begin()/commit()/rollback() themselves.
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
