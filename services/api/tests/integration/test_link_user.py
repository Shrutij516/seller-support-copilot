import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.models import Seller
from copilot_api.scripts.link_user import SellerNotFoundError, link_user_in_session
from tests.integration.factories import create_seller, unit_of_work

pytestmark = pytest.mark.integration


async def test_link_user_sets_cognito_sub(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        seller = await create_seller(session, email="link-me@example.com")
    assert seller.cognito_sub is None

    async with session_factory() as session, unit_of_work(session):
        await link_user_in_session(session, "link-me@example.com", "sub-linked-1")

    async with session_factory() as verify:
        refreshed = await verify.get(Seller, seller.id)
        assert refreshed is not None
        assert refreshed.cognito_sub == "sub-linked-1"


async def test_link_user_unknown_email_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(SellerNotFoundError):
            await link_user_in_session(session, "no-such-seller@example.com", "sub-x")


async def test_link_user_duplicate_sub_raises_without_relinking(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await create_seller(session, email="first@example.com", cognito_sub="sub-taken")
        second = await create_seller(session, email="second@example.com")

    async with session_factory() as session:
        with pytest.raises(IntegrityError):
            await link_user_in_session(session, "second@example.com", "sub-taken")
        await session.rollback()

    async with session_factory() as verify:
        refreshed = await verify.get(Seller, second.id)
        assert refreshed is not None
        assert refreshed.cognito_sub is None
