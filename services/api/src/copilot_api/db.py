from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from copilot_api.config import Settings


def _async_url(database_url: str) -> str:
    # Settings.database_url stays driver-agnostic so it can also be handed to plain tools
    # (psql, alembic's sync engine); SQLAlchemy's async engine needs the driver in the scheme.
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        _async_url(settings.database_url),
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
