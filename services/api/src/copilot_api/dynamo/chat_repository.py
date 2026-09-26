from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from ulid import ULID

from copilot_api.dynamo.table import TABLE_NAME

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

SESSION_TTL_DAYS = 30


@dataclass(frozen=True, slots=True)
class ChatSession:
    session_id: str
    seller_id: str
    title: str
    created_at: datetime
    last_message_at: datetime


@dataclass(frozen=True, slots=True)
class ChatMessage:
    session_id: str
    message_id: str
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"chat session {session_id} not found")
        self.session_id = session_id


def _session_pk(session_id: str) -> str:
    return f"SESSION#{session_id}"


def _seller_gsi1pk(seller_id: str) -> str:
    return f"SELLER#{seller_id}"


def _encode_cursor(key: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return decoded


class ChatRepository:
    """Access patterns 1-4 below; pattern 5 (expire old sessions) needs no method: DynamoDB's
    TTL sweep deletes items past their `expires_at`, refreshed on every message append.
    """

    def __init__(self, client: DynamoDBClient, table_name: str = TABLE_NAME) -> None:
        self._client = client
        self._table_name = table_name

    async def create_session(self, seller_id: str, title: str) -> ChatSession:
        session_id = str(ULID())
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)

        def _put() -> None:
            self._client.put_item(
                TableName=self._table_name,
                Item={
                    "PK": {"S": _session_pk(session_id)},
                    "SK": {"S": "META"},
                    "seller_id": {"S": seller_id},
                    "title": {"S": title},
                    "created_at": {"S": now.isoformat()},
                    "last_message_at": {"S": now.isoformat()},
                    "expires_at": {"N": str(int(expires_at.timestamp()))},
                    "GSI1PK": {"S": _seller_gsi1pk(seller_id)},
                    "GSI1SK": {"S": now.isoformat()},
                },
                ConditionExpression="attribute_not_exists(PK)",
            )

        await asyncio.to_thread(_put)
        return ChatSession(
            session_id=session_id,
            seller_id=seller_id,
            title=title,
            created_at=now,
            last_message_at=now,
        )

    async def append_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        message_id = str(ULID())
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)
        pk = _session_pk(session_id)

        def _write() -> None:
            try:
                self._client.transact_write_items(
                    TransactItems=[
                        {
                            "Put": {
                                "TableName": self._table_name,
                                "Item": {
                                    "PK": {"S": pk},
                                    "SK": {"S": f"MSG#{message_id}"},
                                    "role": {"S": role},
                                    "content": {"S": content},
                                    "created_at": {"S": now.isoformat()},
                                    "expires_at": {"N": str(int(expires_at.timestamp()))},
                                },
                            }
                        },
                        {
                            "Update": {
                                "TableName": self._table_name,
                                "Key": {"PK": {"S": pk}, "SK": {"S": "META"}},
                                "ConditionExpression": "attribute_exists(PK)",
                                "UpdateExpression": (
                                    "SET last_message_at = :now, "
                                    "GSI1SK = :now, "
                                    "expires_at = :expires_at"
                                ),
                                "ExpressionAttributeValues": {
                                    ":now": {"S": now.isoformat()},
                                    ":expires_at": {"N": str(int(expires_at.timestamp()))},
                                },
                            }
                        },
                    ]
                )
            except self._client.exceptions.TransactionCanceledException as exc:
                raise SessionNotFoundError(session_id) from exc

        await asyncio.to_thread(_write)
        return ChatMessage(
            session_id=session_id,
            message_id=message_id,
            role=role,
            content=content,
            created_at=now,
        )

    async def list_messages(
        self, session_id: str, limit: int = 50, cursor: str | None = None
    ) -> Page[ChatMessage]:
        pk = _session_pk(session_id)

        def _query() -> Any:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
                "ExpressionAttributeValues": {":pk": {"S": pk}, ":prefix": {"S": "MSG#"}},
                "Limit": limit,
                "ScanIndexForward": True,
            }
            if cursor:
                kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)
            return self._client.query(**kwargs)

        response = await asyncio.to_thread(_query)
        items = [
            ChatMessage(
                session_id=session_id,
                message_id=item["SK"]["S"].removeprefix("MSG#"),
                role=item["role"]["S"],
                content=item["content"]["S"],
                created_at=datetime.fromisoformat(item["created_at"]["S"]),
            )
            for item in response.get("Items", [])
        ]
        last_key = response.get("LastEvaluatedKey")
        return Page(items=items, next_cursor=_encode_cursor(last_key) if last_key else None)

    async def list_sessions_for_seller(
        self, seller_id: str, limit: int = 20, cursor: str | None = None
    ) -> Page[ChatSession]:
        def _query() -> Any:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "IndexName": "GSI1",
                "KeyConditionExpression": "GSI1PK = :gsi1pk",
                "ExpressionAttributeValues": {":gsi1pk": {"S": _seller_gsi1pk(seller_id)}},
                "Limit": limit,
                "ScanIndexForward": False,
            }
            if cursor:
                kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)
            return self._client.query(**kwargs)

        response = await asyncio.to_thread(_query)
        items = [
            ChatSession(
                session_id=item["PK"]["S"].removeprefix("SESSION#"),
                seller_id=item["seller_id"]["S"],
                title=item["title"]["S"],
                created_at=datetime.fromisoformat(item["created_at"]["S"]),
                last_message_at=datetime.fromisoformat(item["last_message_at"]["S"]),
            )
            for item in response.get("Items", [])
        ]
        last_key = response.get("LastEvaluatedKey")
        return Page(items=items, next_cursor=_encode_cursor(last_key) if last_key else None)
