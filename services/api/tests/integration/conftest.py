"""Isolation for integration tests: a separate Postgres database and a separate DynamoDB
table, so tests never read, write, or truncate the dev/seeded ones. `test_readyz.py` is the
one exception on purpose: it exercises the app's actual configured dependencies (whatever
DATABASE_URL and the "chat" table are in this environment), since that's what a health check
is for.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config as AlembicConfig
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.config import Settings, get_settings
from copilot_api.db import create_engine, create_session_factory
from copilot_api.dynamo.admin import ensure_table
from copilot_api.dynamo.chat_repository import ChatRepository
from copilot_api.dynamo.client import create_dynamodb_client
from copilot_api.dynamo.table import TABLE_SCHEMA

TEST_DB_NAME = "copilot_test"
TEST_TABLE_NAME = "chat_test"

# Truncate in FK-safe order: children before parents.
_APP_TABLES = ("support_cases", "order_items", "orders", "listings", "sellers")

_ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"


def _replace_db_name(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", parts.query, parts.fragment))


def _test_database_url() -> str:
    return _replace_db_name(get_settings().database_url, TEST_DB_NAME)


def _ensure_test_database_exists() -> None:
    maintenance_url = _replace_db_name(get_settings().database_url, "postgres")
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB_NAME)))


def _migrate_test_database() -> None:
    os.environ["TEST_DATABASE_URL"] = _test_database_url()
    try:
        command.upgrade(AlembicConfig(str(_ALEMBIC_INI)), "head")
    finally:
        os.environ.pop("TEST_DATABASE_URL", None)


@pytest.fixture(scope="session", autouse=True)
def _test_postgres_database() -> None:
    _ensure_test_database_exists()
    _migrate_test_database()


@pytest.fixture(scope="session", autouse=True)
def _test_dynamodb_table() -> None:
    client = create_dynamodb_client(get_settings())
    ensure_table(client, {**TABLE_SCHEMA, "TableName": TEST_TABLE_NAME})
    client.close()


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """An engine bound to `copilot_test`, truncated after every test that uses it."""
    engine = create_engine(Settings(database_url=_test_database_url()))
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        async with factory() as session:
            await session.execute(
                text(f"TRUNCATE TABLE {', '.join(_APP_TABLES)} RESTART IDENTITY CASCADE")
            )
            await session.commit()
        await engine.dispose()


@pytest.fixture
def chat_table_name() -> str:
    return TEST_TABLE_NAME


@pytest.fixture
def repo() -> ChatRepository:
    """A ChatRepository bound to the isolated "chat_test" table, never the dev "chat" one."""
    client = create_dynamodb_client(get_settings())
    return ChatRepository(client, table_name=TEST_TABLE_NAME)
