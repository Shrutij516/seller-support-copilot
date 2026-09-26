"""Isolation for integration tests: a separate Postgres database and a separate DynamoDB
table, so tests never read, write, or truncate the dev/seeded ones. `test_readyz.py` is the
one exception on purpose: it exercises the app's actual configured dependencies (whatever
DATABASE_URL and the "chat" table are in this environment), since that's what a health check
is for.
"""

import json
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import jwt
import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config as AlembicConfig
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.auth import JWKSCache, get_jwks_cache
from copilot_api.config import Settings, get_settings
from copilot_api.db import create_engine, create_session_factory
from copilot_api.deps import get_db_session
from copilot_api.dynamo.admin import ensure_table
from copilot_api.dynamo.chat_repository import ChatRepository
from copilot_api.dynamo.client import create_dynamodb_client
from copilot_api.dynamo.table import TABLE_SCHEMA
from copilot_api.main import app as fastapi_app
from copilot_api.routers.chat import get_chat_repo

TEST_DB_NAME = "copilot_test"
TEST_TABLE_NAME = "chat_test"

TEST_ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TESTPOOL"
TEST_CLIENT_ID = "test-app-client-id"
TEST_KID = "test-key-1"

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


# --- Auth test infrastructure: a locally generated RSA key and a fake JWKS. No AWS calls,
# no real Cognito user pool; every token in these tests is minted by us. ---


@pytest.fixture(scope="session")
def rsa_keypair() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_rsa_keypair() -> RSAPrivateKey:
    """A second, unrelated key: tokens signed with this one must fail signature checks
    against the real JWKS, whether or not its `kid` happens to collide.
    """
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_for(key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid=kid, use="sig", alg="RS256")
    return jwk


@pytest_asyncio.fixture
async def jwks_cache(rsa_keypair: RSAPrivateKey) -> AsyncIterator[JWKSCache]:
    cache = JWKSCache.for_testing({"keys": [_jwk_for(rsa_keypair, TEST_KID)]})
    try:
        yield cache
    finally:
        await cache.aclose()


def mint_token(
    rsa_keypair: RSAPrivateKey,
    *,
    sub: str = "test-sub-0000",
    groups: list[str] | None = None,
    token_use: str = "access",
    client_id: str = TEST_CLIENT_ID,
    issuer: str = TEST_ISSUER,
    kid: str = TEST_KID,
    expires_in: timedelta = timedelta(hours=1),
    algorithm: str = "RS256",
    signing_key: RSAPrivateKey | None = None,
) -> str:
    """Mint a JWT shaped like a Cognito access token, with every field overridable so each
    401 test case can break exactly one thing.
    """
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": sub,
        "iss": issuer,
        "token_use": token_use,
        "client_id": client_id,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
    }
    if groups is not None:
        claims["cognito:groups"] = groups
    key = signing_key if signing_key is not None else rsa_keypair
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": kid})


@pytest.fixture
def api_client(
    session_factory: async_sessionmaker[AsyncSession], jwks_cache: JWKSCache
) -> Iterator[TestClient]:
    """A TestClient against the real app, with only the "plumbing" dependencies redirected
    to test infrastructure (isolated DB, isolated chat table, local JWKS). Auth itself
    (get_current_principal, require_role, ...) runs for real against minted tokens.
    """
    test_settings = Settings(cognito_issuer=TEST_ISSUER, cognito_app_client_id=TEST_CLIENT_ID)
    test_chat_repo = ChatRepository(
        create_dynamodb_client(get_settings()), table_name=TEST_TABLE_NAME
    )

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_settings] = lambda: test_settings
    fastapi_app.dependency_overrides[get_jwks_cache] = lambda: jwks_cache
    fastapi_app.dependency_overrides[get_db_session] = _override_get_db_session
    fastapi_app.dependency_overrides[get_chat_repo] = lambda: test_chat_repo
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()
