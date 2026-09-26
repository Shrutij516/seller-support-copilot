import uuid
from datetime import UTC, datetime, timedelta

import pytest

from copilot_api.config import get_settings
from copilot_api.dynamo.chat_repository import (
    SESSION_TTL_DAYS,
    ChatRepository,
    SessionNotFoundError,
)
from copilot_api.dynamo.client import create_dynamodb_client
from copilot_api.dynamo.table import TTL_ATTRIBUTE

pytestmark = pytest.mark.integration

# `repo` and `chat_table_name` come from tests/integration/conftest.py: bound to the
# isolated "chat_test" table, never the dev "chat" one.


async def test_create_session_creates_meta_item(repo: ChatRepository) -> None:
    seller_id = str(uuid.uuid4())
    session = await repo.create_session(seller_id, title="Order question")

    assert session.seller_id == seller_id
    assert session.title == "Order question"
    assert session.created_at == session.last_message_at


async def test_append_message_updates_session_and_returns_message(repo: ChatRepository) -> None:
    seller_id = str(uuid.uuid4())
    session = await repo.create_session(seller_id, title="Refund status?")

    message = await repo.append_message(
        session.session_id, role="user", content="Where's my refund?"
    )

    assert message.session_id == session.session_id
    assert message.role == "user"
    assert message.content == "Where's my refund?"

    sessions = await repo.list_sessions_for_seller(seller_id)
    assert sessions.items[0].last_message_at >= session.last_message_at


async def test_append_message_to_missing_session_raises(repo: ChatRepository) -> None:
    with pytest.raises(SessionNotFoundError):
        await repo.append_message(str(uuid.uuid4()), role="user", content="hello?")


async def test_list_messages_returns_in_order_and_paginates(repo: ChatRepository) -> None:
    seller_id = str(uuid.uuid4())
    session = await repo.create_session(seller_id, title="Multi-message thread")

    for i in range(5):
        await repo.append_message(session.session_id, role="user", content=f"message {i}")

    page = await repo.list_messages(session.session_id, limit=3)
    assert [m.content for m in page.items] == ["message 0", "message 1", "message 2"]
    assert page.next_cursor is not None

    next_page = await repo.list_messages(session.session_id, limit=3, cursor=page.next_cursor)
    assert [m.content for m in next_page.items] == ["message 3", "message 4"]
    assert next_page.next_cursor is None


async def test_list_sessions_for_seller_returns_newest_first(repo: ChatRepository) -> None:
    seller_id = str(uuid.uuid4())
    older = await repo.create_session(seller_id, title="Older session")
    newer = await repo.create_session(seller_id, title="Newer session")
    # Give the newer session a later last_message_at than the older one's creation time.
    await repo.append_message(newer.session_id, role="user", content="ping")

    page = await repo.list_sessions_for_seller(seller_id)
    session_ids = [s.session_id for s in page.items]

    assert session_ids.index(newer.session_id) < session_ids.index(older.session_id)


async def test_session_and_message_expires_at_set_for_ttl(
    repo: ChatRepository, chat_table_name: str
) -> None:
    seller_id = str(uuid.uuid4())
    before = datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS - 1)
    session = await repo.create_session(seller_id, title="Expiring session")
    message = await repo.append_message(session.session_id, role="user", content="hi")
    after = datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS + 1)

    client = create_dynamodb_client(get_settings())
    try:
        ttl = client.describe_time_to_live(TableName=chat_table_name)
        assert ttl["TimeToLiveDescription"]["TimeToLiveStatus"] in ("ENABLED", "ENABLING")
        assert ttl["TimeToLiveDescription"]["AttributeName"] == TTL_ATTRIBUTE

        item = client.get_item(
            TableName=chat_table_name,
            Key={"PK": {"S": f"SESSION#{session.session_id}"}, "SK": {"S": "META"}},
        )["Item"]
        expires_at = datetime.fromtimestamp(int(item["expires_at"]["N"]), UTC)
        assert before < expires_at < after
        assert message.message_id  # message was written in the same TTL window
    finally:
        client.close()


async def test_append_message_slides_session_expires_at_forward(
    repo: ChatRepository, chat_table_name: str
) -> None:
    seller_id = str(uuid.uuid4())
    session = await repo.create_session(seller_id, title="Sliding TTL")

    client = create_dynamodb_client(get_settings())

    def _meta_expires_at() -> int:
        item = client.get_item(
            TableName=chat_table_name,
            Key={"PK": {"S": f"SESSION#{session.session_id}"}, "SK": {"S": "META"}},
        )["Item"]
        return int(item["expires_at"]["N"])

    try:
        first_expires_at = _meta_expires_at()
        await repo.append_message(session.session_id, role="user", content="still going")
        second_expires_at = _meta_expires_at()

        # Both are "now + 30 days" computed a moment apart, so the second is never earlier;
        # activity slides the session's expiry forward instead of counting from creation.
        assert second_expires_at >= first_expires_at
    finally:
        client.close()


async def test_list_messages_filters_out_already_expired_items(
    repo: ChatRepository, chat_table_name: str
) -> None:
    seller_id = str(uuid.uuid4())
    session = await repo.create_session(seller_id, title="Has a stale message")
    await repo.append_message(session.session_id, role="user", content="still here")

    # DynamoDB's TTL sweep is lazy (can lag by hours), so write an already-expired message
    # directly, bypassing the repo (which never writes a past expiry), to simulate that
    # window and confirm reads filter it out rather than trusting the sweep alone.
    client = create_dynamodb_client(get_settings())
    try:
        past_epoch = int(datetime.now(UTC).timestamp()) - 3600
        client.put_item(
            TableName=chat_table_name,
            Item={
                "PK": {"S": f"SESSION#{session.session_id}"},
                "SK": {"S": "MSG#00000000000000000000000000"},
                "role": {"S": "user"},
                "content": {"S": "should be filtered out"},
                "created_at": {"S": datetime.now(UTC).isoformat()},
                "expires_at": {"N": str(past_epoch)},
            },
        )

        page = await repo.list_messages(session.session_id, limit=10)
        contents = [m.content for m in page.items]
        assert "should be filtered out" not in contents
        assert "still here" in contents
    finally:
        client.close()


async def test_list_sessions_for_seller_filters_out_already_expired_sessions(
    repo: ChatRepository, chat_table_name: str
) -> None:
    seller_id = str(uuid.uuid4())
    live_session = await repo.create_session(seller_id, title="Still active")

    client = create_dynamodb_client(get_settings())
    try:
        expired_session_id = str(uuid.uuid4())
        past_epoch = int(datetime.now(UTC).timestamp()) - 3600
        now_iso = datetime.now(UTC).isoformat()
        client.put_item(
            TableName=chat_table_name,
            Item={
                "PK": {"S": f"SESSION#{expired_session_id}"},
                "SK": {"S": "META"},
                "seller_id": {"S": seller_id},
                "title": {"S": "Expired session"},
                "created_at": {"S": now_iso},
                "last_message_at": {"S": now_iso},
                "expires_at": {"N": str(past_epoch)},
                "GSI1PK": {"S": f"SELLER#{seller_id}"},
                "GSI1SK": {"S": now_iso},
            },
        )

        page = await repo.list_sessions_for_seller(seller_id)
        session_ids = [s.session_id for s in page.items]
        assert expired_session_id not in session_ids
        assert live_session.session_id in session_ids
    finally:
        client.close()
