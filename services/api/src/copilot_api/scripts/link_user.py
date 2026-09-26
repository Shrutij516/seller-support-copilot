"""Link a seed seller to a real Cognito user, for local login testing ahead of phase 3.

Run via `make link-user EMAIL=<seed seller email> SUB=<cognito sub>`. Refuses to run
against APP_ENV=prod.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.config import get_settings
from copilot_api.db import create_engine, create_session_factory
from copilot_api.models import Seller


class SellerNotFoundError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"no seller found with email {email!r}")
        self.email = email


async def link_user_in_session(session: AsyncSession, email: str, cognito_sub: str) -> Seller:
    """The actual update, given an open session. Testable independent of settings, engine
    creation, or the APP_ENV guard. Caller commits/rolls back (see `link_user` below).
    """
    seller = (
        await session.execute(select(Seller).where(Seller.email == email))
    ).scalar_one_or_none()
    if seller is None:
        raise SellerNotFoundError(email)
    seller.cognito_sub = cognito_sub
    await session.flush()
    return seller


async def link_user(email: str, cognito_sub: str) -> None:
    settings = get_settings()
    if settings.app_env == "prod":
        print("Refusing to link a user: APP_ENV=prod", file=sys.stderr)
        raise SystemExit(1)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            try:
                await link_user_in_session(session, email, cognito_sub)
                await session.commit()
            except SellerNotFoundError as exc:
                await session.rollback()
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from None
            except IntegrityError:
                await session.rollback()
                print(
                    f"cognito_sub {cognito_sub!r} is already linked to another seller",
                    file=sys.stderr,
                )
                raise SystemExit(1) from None
    finally:
        await engine.dispose()

    print(f"linked {email} -> cognito_sub={cognito_sub}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Existing seller's email")
    parser.add_argument("--sub", required=True, help="Cognito sub (the 'sub' JWT claim)")
    args = parser.parse_args()
    asyncio.run(link_user(args.email, args.sub))


if __name__ == "__main__":
    main()
