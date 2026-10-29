from __future__ import annotations

import asyncio
import base64
import hashlib
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
class Citation:
    """One numbered source behind an assistant answer: `index` matches the [n] markers the
    model was told to cite with.
    """

    index: int
    source: str
    snippet: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    session_id: str
    message_id: str
    role: str
    content: str
    created_at: datetime
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"chat session {session_id} not found")
        self.session_id = session_id


class IdempotencyKeyReusedError(Exception):
    """The same client_message_id was sent again with different content: a client bug, not a
    retry, so it's rejected rather than silently answered as the original question.
    """

    def __init__(self, session_id: str, client_message_id: str) -> None:
        super().__init__(f"client_message_id {client_message_id} reused with different content")
        self.session_id = session_id
        self.client_message_id = client_message_id


@dataclass(frozen=True, slots=True)
class StoredQuestion:
    """Result of store_question_once. `replayed` is True when this client_message_id was seen
    before in this session (no new user message was written); `existing_answer` is the answer
    already recorded for it, if any, so the caller can return it without calling the model.
    """

    replayed: bool
    existing_answer: ChatMessage | None


def _session_pk(session_id: str) -> str:
    return f"SESSION#{session_id}"


def _seller_gsi1pk(seller_id: str) -> str:
    return f"SELLER#{seller_id}"


def _encode_cursor(key: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return decoded


# Condition for linking an answer to a REQ# item: the item exists and has no answer yet.
_ANSWER_NOT_YET_LINKED = "attribute_exists(PK) AND attribute_not_exists(assistant_message_id)"


def _request_sk(client_message_id: str) -> str:
    # Per-session idempotency item; not under MSG#, so message listing never sees it.
    return f"REQ#{client_message_id}"


def _content_digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _cancellation_codes(exc: Exception) -> list[str]:
    """Per-item reasons from a TransactionCanceledException, in TransactItems order."""
    response: dict[str, Any] = getattr(exc, "response", {}) or {}
    return [reason.get("Code", "None") for reason in response.get("CancellationReasons", [])]


def _encode_citations(citations: tuple[Citation, ...]) -> str:
    return json.dumps(
        [{"index": c.index, "source": c.source, "snippet": c.snippet} for c in citations]
    )


def _decode_citations(item: dict[str, Any]) -> tuple[Citation, ...]:
    # Absent on user messages and on anything written before citations existed.
    raw = item.get("citations")
    if raw is None:
        return ()
    return tuple(
        Citation(index=c["index"], source=c["source"], snippet=c["snippet"])
        for c in json.loads(raw["S"])
    )


class ChatRepository:
    """Access patterns 1-4 below; pattern 5 (expire old sessions) needs no method: DynamoDB's
    TTL sweep deletes items past their `expires_at`, refreshed (sliding, 30 days from last
    activity) on every message append. TTL deletion is lazy, sometimes by hours, so reads
    also filter out anything already past its `expires_at` that the sweep hasn't caught yet.
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

    async def get_session(self, session_id: str) -> ChatSession | None:
        """Used for ownership checks: None both when the session never existed and when
        it's past its expires_at (treated as already gone, consistent with the read filters
        below, even if the TTL sweep hasn't physically deleted it yet).
        """

        def _get() -> Any:
            return self._client.get_item(
                TableName=self._table_name,
                Key={"PK": {"S": _session_pk(session_id)}, "SK": {"S": "META"}},
            )

        response = await asyncio.to_thread(_get)
        item = response.get("Item")
        if item is None:
            return None
        if int(item["expires_at"]["N"]) <= int(datetime.now(UTC).timestamp()):
            return None
        return ChatSession(
            session_id=session_id,
            seller_id=item["seller_id"]["S"],
            title=item["title"]["S"],
            created_at=datetime.fromisoformat(item["created_at"]["S"]),
            last_message_at=datetime.fromisoformat(item["last_message_at"]["S"]),
        )

    def _message_item(
        self,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        now: datetime,
        citations: tuple[Citation, ...] = (),
    ) -> dict[str, Any]:
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)
        item: dict[str, Any] = {
            "PK": {"S": _session_pk(session_id)},
            "SK": {"S": f"MSG#{message_id}"},
            "role": {"S": role},
            "content": {"S": content},
            "created_at": {"S": now.isoformat()},
            "expires_at": {"N": str(int(expires_at.timestamp()))},
        }
        if citations:
            item["citations"] = {"S": _encode_citations(citations)}
        return item

    def _touch_session(self, session_id: str, now: datetime) -> Any:  # a TransactWriteItem
        """TransactItem: bump last_message_at and slide the TTL; fails if the session's gone."""
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)
        return {
            "Update": {
                "TableName": self._table_name,
                "Key": {"PK": {"S": _session_pk(session_id)}, "SK": {"S": "META"}},
                "ConditionExpression": "attribute_exists(PK)",
                "UpdateExpression": (
                    "SET last_message_at = :now, GSI1SK = :now, expires_at = :expires_at"
                ),
                "ExpressionAttributeValues": {
                    ":now": {"S": now.isoformat()},
                    ":expires_at": {"N": str(int(expires_at.timestamp()))},
                },
            }
        }

    @staticmethod
    def _to_message(session_id: str, item: dict[str, Any]) -> ChatMessage:
        return ChatMessage(
            session_id=session_id,
            message_id=item["SK"]["S"].removeprefix("MSG#"),
            role=item["role"]["S"],
            content=item["content"]["S"],
            created_at=datetime.fromisoformat(item["created_at"]["S"]),
            citations=_decode_citations(item),
        )

    async def _get_item(self, session_id: str, sk: str) -> dict[str, Any] | None:
        def _get() -> Any:
            return self._client.get_item(
                TableName=self._table_name,
                Key={"PK": {"S": _session_pk(session_id)}, "SK": {"S": sk}},
                ConsistentRead=True,
            )

        response = await asyncio.to_thread(_get)
        item: dict[str, Any] | None = response.get("Item")
        return item

    async def _answer_for_request(
        self, session_id: str, request: dict[str, Any]
    ) -> ChatMessage | None:
        answer_id = request.get("assistant_message_id", {}).get("S")
        if not answer_id:
            return None
        item = await self._get_item(session_id, f"MSG#{answer_id}")
        return self._to_message(session_id, item) if item else None

    async def store_question_once(
        self, session_id: str, client_message_id: str, content: str
    ) -> StoredQuestion:
        """Store the user's question at most once per (session, client_message_id).

        One TransactWriteItems: Put the REQ# idempotency item (condition: it doesn't exist yet),
        Put the user message, and touch the session. All three or none, so there is never a
        stored question without its idempotency item (or vice versa), and two concurrent sends
        with the same id can't both win. A repeat fails the first condition and writes nothing;
        it then reads the REQ# item to report whether an answer already exists.
        """
        now = datetime.now(UTC)
        message_id = str(ULID())
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)
        request_item: dict[str, Any] = {
            "PK": {"S": _session_pk(session_id)},
            "SK": {"S": _request_sk(client_message_id)},
            "user_message_id": {"S": message_id},
            "content_sha256": {"S": _content_digest(content)},
            "created_at": {"S": now.isoformat()},
            "expires_at": {"N": str(int(expires_at.timestamp()))},
        }

        def _write() -> None:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": request_item,
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": self._message_item(
                                session_id, message_id, "user", content, now
                            ),
                        }
                    },
                    self._touch_session(session_id, now),
                ]
            )

        try:
            await asyncio.to_thread(_write)
        except self._client.exceptions.TransactionCanceledException as exc:
            codes = _cancellation_codes(exc)
            if len(codes) > 2 and codes[2] == "ConditionalCheckFailed":
                raise SessionNotFoundError(session_id) from exc
            if codes and codes[0] == "ConditionalCheckFailed":
                existing = await self._get_item(session_id, _request_sk(client_message_id))
                if existing is None:  # expired between the write and the read
                    raise SessionNotFoundError(session_id) from exc
                if existing["content_sha256"]["S"] != _content_digest(content):
                    raise IdempotencyKeyReusedError(session_id, client_message_id) from exc
                return StoredQuestion(
                    replayed=True,
                    existing_answer=await self._answer_for_request(session_id, existing),
                )
            raise
        return StoredQuestion(replayed=False, existing_answer=None)

    async def store_answer_once(
        self,
        session_id: str,
        client_message_id: str,
        content: str,
        citations: tuple[Citation, ...] = (),
    ) -> ChatMessage:
        """Store the assistant answer for a question and link it from the REQ# item, at most
        once: the REQ# update is conditioned on no answer being linked yet. If a concurrent
        request already recorded one, nothing is written and that answer is returned instead.
        """
        now = datetime.now(UTC)
        message_id = str(ULID())

        def _write() -> None:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": self._message_item(
                                session_id, message_id, "assistant", content, now, citations
                            ),
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": {
                                "PK": {"S": _session_pk(session_id)},
                                "SK": {"S": _request_sk(client_message_id)},
                            },
                            "ConditionExpression": _ANSWER_NOT_YET_LINKED,
                            "UpdateExpression": "SET assistant_message_id = :id",
                            "ExpressionAttributeValues": {":id": {"S": message_id}},
                        }
                    },
                    self._touch_session(session_id, now),
                ]
            )

        try:
            await asyncio.to_thread(_write)
        except self._client.exceptions.TransactionCanceledException as exc:
            codes = _cancellation_codes(exc)
            if len(codes) > 2 and codes[2] == "ConditionalCheckFailed":
                raise SessionNotFoundError(session_id) from exc
            if len(codes) > 1 and codes[1] == "ConditionalCheckFailed":
                existing = await self._get_item(session_id, _request_sk(client_message_id))
                answer = await self._answer_for_request(session_id, existing) if existing else None
                if answer is None:
                    raise SessionNotFoundError(session_id) from exc
                return answer
            raise
        return ChatMessage(
            session_id=session_id,
            message_id=message_id,
            role="assistant",
            content=content,
            created_at=now,
            citations=citations,
        )

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: tuple[Citation, ...] = (),
    ) -> ChatMessage:
        message_id = str(ULID())
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)
        pk = _session_pk(session_id)
        message_item: dict[str, Any] = {
            "PK": {"S": pk},
            "SK": {"S": f"MSG#{message_id}"},
            "role": {"S": role},
            "content": {"S": content},
            "created_at": {"S": now.isoformat()},
            "expires_at": {"N": str(int(expires_at.timestamp()))},
        }
        if citations:
            message_item["citations"] = {"S": _encode_citations(citations)}

        def _write() -> None:
            try:
                self._client.transact_write_items(
                    TransactItems=[
                        {
                            "Put": {
                                "TableName": self._table_name,
                                "Item": message_item,
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
            citations=citations,
        )

    async def list_messages(
        self, session_id: str, limit: int = 50, cursor: str | None = None
    ) -> Page[ChatMessage]:
        pk = _session_pk(session_id)
        now_epoch = str(int(datetime.now(UTC).timestamp()))

        def _query() -> Any:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
                "FilterExpression": "expires_at > :now",
                "ExpressionAttributeValues": {
                    ":pk": {"S": pk},
                    ":prefix": {"S": "MSG#"},
                    ":now": {"N": now_epoch},
                },
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
                citations=_decode_citations(item),
            )
            for item in response.get("Items", [])
        ]
        last_key = response.get("LastEvaluatedKey")
        return Page(items=items, next_cursor=_encode_cursor(last_key) if last_key else None)

    async def list_sessions_for_seller(
        self, seller_id: str, limit: int = 20, cursor: str | None = None
    ) -> Page[ChatSession]:
        now_epoch = str(int(datetime.now(UTC).timestamp()))

        def _query() -> Any:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "IndexName": "GSI1",
                "KeyConditionExpression": "GSI1PK = :gsi1pk",
                "FilterExpression": "expires_at > :now",
                "ExpressionAttributeValues": {
                    ":gsi1pk": {"S": _seller_gsi1pk(seller_id)},
                    ":now": {"N": now_epoch},
                },
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
