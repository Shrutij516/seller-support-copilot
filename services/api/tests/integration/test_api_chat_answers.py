"""POST /v1/chat/sessions/{id}/messages against the real app, Postgres, and DynamoDB Local,
with the Retriever and Generator replaced by in-memory fakes. No Bedrock calls, no moto.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from copilot_api.config import Settings, get_settings
from copilot_api.main import app as fastapi_app
from copilot_api.rag.prompt import REFUSAL_MESSAGE, SYSTEM_PROMPT
from copilot_api.rag.types import Generation, RagBackendError, RetrievedChunk
from copilot_api.routers.chat import get_generator, get_retriever
from tests.integration.conftest import TEST_CLIENT_ID, TEST_ISSUER, mint_token
from tests.integration.factories import create_seller

pytestmark = pytest.mark.integration

MIN_SCORE = 0.5
QUESTION = "How long do refunds take?"
ANSWER = "Refunds are issued within 5 business days [1]."


@dataclass
class FakeRetriever:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    error: RagBackendError | None = None
    calls: list[str] = field(default_factory=list)

    async def retrieve(self, query: str) -> list[RetrievedChunk]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.chunks


@dataclass
class FakeGenerator:
    answer: str = ANSWER
    error: RagBackendError | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def generate(self, system_prompt: str, user_message: str) -> Generation:
        self.calls.append((system_prompt, user_message))
        if self.error is not None:
            raise self.error
        return Generation(self.answer)


@pytest.fixture
def retriever() -> FakeRetriever:
    return FakeRetriever(
        chunks=[
            RetrievedChunk(text="R" * 500, source="returns-and-refunds.md", score=0.9),
            RetrievedChunk(text="Fees are charged at sale.", source="fees.md", score=0.7),
        ]
    )


@pytest.fixture
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def client(
    api_client: TestClient, retriever: FakeRetriever, generator: FakeGenerator
) -> Iterator[TestClient]:
    # api_client already overrides get_settings for auth; replace it with the same auth
    # values plus an explicit min score, so these tests don't depend on the default.
    settings = Settings(
        cognito_issuer=TEST_ISSUER, cognito_app_client_id=TEST_CLIENT_ID, rag_min_score=MIN_SCORE
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    fastapi_app.dependency_overrides[get_retriever] = lambda: retriever
    fastapi_app.dependency_overrides[get_generator] = lambda: generator
    yield api_client


async def _seller_with_session(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    sub: str,
) -> tuple[dict[str, str], str]:
    async with session_factory() as session, session.begin():
        await create_seller(session, cognito_sub=sub)
    headers = {"Authorization": f"Bearer {mint_token(rsa_keypair, sub=sub, groups=['seller'])}"}
    created = client.post("/v1/chat/sessions", json={"title": "Refunds"}, headers=headers)
    assert created.status_code == 201
    return headers, created.json()["session_id"]


def _post(
    client: TestClient,
    session_id: str,
    headers: dict[str, str],
    content: Any,
    client_message_id: str | None = None,
) -> Any:
    """A fresh client_message_id per call unless one is given (a retry reuses it)."""
    body = {"content": content, "client_message_id": client_message_id or str(uuid.uuid4())}
    return client.post(f"/v1/chat/sessions/{session_id}/messages", json=body, headers=headers)


def _stored(client: TestClient, session_id: str, headers: dict[str, str]) -> list[Any]:
    response = client.get(f"/v1/chat/sessions/{session_id}/messages", headers=headers)
    assert response.status_code == 200
    items: list[Any] = response.json()["items"]
    return items


async def test_answer_with_citations_and_both_messages_persisted_in_order(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> None:
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-rag-happy"
    )

    response = _post(client, session_id, headers, QUESTION)

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"] == ANSWER
    # Two chunks went to the model; the answer cites only [1], so only [1] comes back.
    assert [(c["index"], c["source"]) for c in body["citations"]] == [
        (1, "returns-and-refunds.md"),
    ]
    assert body["citations"][0]["snippet"] == "R" * 300

    assert retriever.calls == [QUESTION]
    assert len(generator.calls) == 1
    system_prompt, user_message = generator.calls[0]
    assert system_prompt == SYSTEM_PROMPT
    assert "[1] (source: returns-and-refunds.md)" in user_message
    assert "[2] (source: fees.md)" in user_message

    stored = _stored(client, session_id, headers)
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", QUESTION),
        ("assistant", ANSWER),
    ]
    assert stored[0]["citations"] == []
    assert stored[1]["citations"] == body["citations"]


async def test_no_chunks_returns_refusal_without_calling_model(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> None:
    retriever.chunks = []
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-rag-empty"
    )

    response = _post(client, session_id, headers, QUESTION)

    assert response.status_code == 201
    assert response.json()["content"] == REFUSAL_MESSAGE
    assert response.json()["citations"] == []
    assert generator.calls == []
    assert [(m["role"], m["content"]) for m in _stored(client, session_id, headers)] == [
        ("user", QUESTION),
        ("assistant", REFUSAL_MESSAGE),
    ]


async def test_chunks_below_min_score_are_dropped(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> None:
    retriever.chunks = [
        RetrievedChunk(text="Relevant refund policy.", source="returns.md", score=0.8),
        RetrievedChunk(text="Barely related fee text.", source="fees.md", score=MIN_SCORE - 0.01),
    ]
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-rag-filter"
    )

    response = _post(client, session_id, headers, QUESTION)

    assert response.status_code == 201
    assert len(generator.calls) == 1
    _, user_message = generator.calls[0]
    assert "Relevant refund policy." in user_message
    assert "Barely related fee text." not in user_message


async def test_all_chunks_below_min_score_returns_refusal_without_calling_model(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> None:
    retriever.chunks = [
        RetrievedChunk(text="Off-topic.", source="fees.md", score=0.1),
        RetrievedChunk(text="Also off-topic.", source="disputes.md", score=MIN_SCORE - 0.01),
    ]
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-rag-allbelow"
    )

    response = _post(client, session_id, headers, QUESTION)

    assert response.status_code == 201
    assert response.json()["content"] == REFUSAL_MESSAGE
    assert generator.calls == []


async def test_other_sellers_session_is_404_and_nothing_runs(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> None:
    owner_headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-rag-owner"
    )
    async with session_factory() as session, session.begin():
        await create_seller(session, cognito_sub="sub-rag-intruder")
    intruder_token = mint_token(rsa_keypair, sub="sub-rag-intruder", groups=["seller"])
    intruder = {"Authorization": f"Bearer {intruder_token}"}

    response = _post(client, session_id, intruder, QUESTION)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert retriever.calls == []
    assert generator.calls == []
    assert _stored(client, session_id, owner_headers) == []


async def test_missing_session_is_404(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    generator: FakeGenerator,
) -> None:
    headers, _ = await _seller_with_session(client, session_factory, rsa_keypair, "sub-rag-nos")

    response = _post(client, "01NOSUCHSESSION0000000000", headers, QUESTION)

    assert response.status_code == 404
    assert generator.calls == []


async def test_unauthenticated_is_401(client: TestClient, generator: FakeGenerator) -> None:
    response = client.post(
        "/v1/chat/sessions/any/messages",
        json={"content": QUESTION, "client_message_id": str(uuid.uuid4())},
    )

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert generator.calls == []


async def test_admin_token_is_403(
    client: TestClient, rsa_keypair: RSAPrivateKey, generator: FakeGenerator
) -> None:
    token = mint_token(rsa_keypair, sub="sub-rag-admin", groups=["admin"])

    response = client.post(
        "/v1/chat/sessions/any/messages",
        json={"content": QUESTION, "client_message_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert generator.calls == []


@pytest.mark.parametrize("content", ["", "   ", "x" * 2001])
async def test_empty_or_too_long_content_is_422(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    content: str,
) -> None:
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, f"sub-rag-422-{len(content)}"
    )

    response = _post(client, session_id, headers, content)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert retriever.calls == []
    assert _stored(client, session_id, headers) == []


async def test_content_at_max_length_is_accepted(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
) -> None:
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-rag-max"
    )

    assert _post(client, session_id, headers, "x" * 2000).status_code == 201


@pytest.mark.parametrize("failing", ["retriever", "generator"])
async def test_backend_failure_is_503_and_no_assistant_message_stored(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
    failing: str,
) -> None:
    if failing == "retriever":
        retriever.error = RagBackendError("retrieve", "ThrottlingException")
    else:
        generator.error = RagBackendError("converse", "ModelTimeoutException")
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, f"sub-rag-503-{failing}"
    )

    response = _post(client, session_id, headers, QUESTION)

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 503
    assert body["request_id"] == response.headers["X-Request-ID"]
    # Internal failure details stay in the logs, never in the response.
    assert "Exception" not in response.text
    assert "Traceback" not in response.text
    if failing == "retriever":
        assert generator.calls == []
    assert [(m["role"], m["content"]) for m in _stored(client, session_id, headers)] == [
        ("user", QUESTION),
    ]


# --- Idempotent send (client_message_id) -----------------------------------------------------


async def test_retry_after_503_stores_the_question_once(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> None:
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-idem-503"
    )
    key = str(uuid.uuid4())

    retriever.error = RagBackendError("retrieve", "ThrottlingException")
    first = _post(client, session_id, headers, QUESTION, key)
    assert first.status_code == 503
    assert [m["role"] for m in _stored(client, session_id, headers)] == ["user"]

    retriever.error = None
    retry = _post(client, session_id, headers, QUESTION, key)

    assert retry.status_code == 201
    assert retry.json()["content"] == ANSWER
    assert [(m["role"], m["content"]) for m in _stored(client, session_id, headers)] == [
        ("user", QUESTION),
        ("assistant", ANSWER),
    ]
    assert len(generator.calls) == 1  # the 503 attempt never reached the model


async def test_retry_after_success_returns_same_answer_without_calling_model(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> None:
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-idem-ok"
    )
    key = str(uuid.uuid4())

    first = _post(client, session_id, headers, QUESTION, key)
    again = _post(client, session_id, headers, QUESTION, key)

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert len(generator.calls) == 1
    assert len(retriever.calls) == 1
    assert [m["role"] for m in _stored(client, session_id, headers)] == ["user", "assistant"]


async def test_different_ids_store_separate_questions(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    generator: FakeGenerator,
) -> None:
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-idem-two"
    )

    assert _post(client, session_id, headers, QUESTION, str(uuid.uuid4())).status_code == 201
    assert _post(client, session_id, headers, QUESTION, str(uuid.uuid4())).status_code == 201

    assert [m["role"] for m in _stored(client, session_id, headers)] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert len(generator.calls) == 2


async def test_same_id_in_another_session_is_independent(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    generator: FakeGenerator,
) -> None:
    headers, first_session = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-idem-cross"
    )
    second = client.post("/v1/chat/sessions", json={"title": "Second"}, headers=headers)
    assert second.status_code == 201
    second_session = second.json()["session_id"]
    key = str(uuid.uuid4())

    assert _post(client, first_session, headers, QUESTION, key).status_code == 201
    assert _post(client, second_session, headers, QUESTION, key).status_code == 201

    for session_id in (first_session, second_session):
        assert [m["role"] for m in _stored(client, session_id, headers)] == ["user", "assistant"]
    assert len(generator.calls) == 2


async def test_same_id_with_different_content_is_409(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    generator: FakeGenerator,
) -> None:
    headers, session_id = await _seller_with_session(
        client, session_factory, rsa_keypair, "sub-idem-409"
    )
    key = str(uuid.uuid4())
    assert _post(client, session_id, headers, QUESTION, key).status_code == 201

    response = _post(client, session_id, headers, "A completely different question?", key)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert len(generator.calls) == 1
    assert [m["role"] for m in _stored(client, session_id, headers)] == ["user", "assistant"]


@pytest.mark.parametrize(
    "body",
    [
        {"content": QUESTION},
        {"content": QUESTION, "client_message_id": "not-a-uuid"},
        {"content": QUESTION, "client_message_id": ""},
    ],
    ids=["missing", "not-a-uuid", "empty"],
)
async def test_missing_or_invalid_client_message_id_is_422(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
    rsa_keypair: RSAPrivateKey,
    retriever: FakeRetriever,
    body: dict[str, str],
) -> None:
    headers, session_id = await _seller_with_session(
        client,
        session_factory,
        rsa_keypair,
        f"sub-idem-422-{len(body)}-{body.get('client_message_id', 'x')[:3]}",
    )

    response = client.post(f"/v1/chat/sessions/{session_id}/messages", json=body, headers=headers)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert retriever.calls == []
    assert _stored(client, session_id, headers) == []
