"""Single source for the "chat" table's shape.

Used by `make dynamodb-init` (services/api/scripts/dynamodb_init.py) against DynamoDB Local,
and by the AWS runbook when this table is created for real. Keep this the only place that
knows the key schema.

Item shapes:
  Session (one per chat session):
    PK=SESSION#<id>  SK=META
    seller_id, title, created_at, last_message_at, expires_at, GSI1PK=SELLER#<seller_id>,
    GSI1SK=<last_message_at>

  Message (many per chat session):
    PK=SESSION#<id>  SK=MSG#<ULID>
    role, content, created_at, expires_at
    (no GSI1PK/GSI1SK: keeps GSI1 sparse, containing only session items)
"""

from typing import Any

TABLE_NAME = "chat"
TTL_ATTRIBUTE = "expires_at"

TABLE_SCHEMA: dict[str, Any] = {
    "TableName": TABLE_NAME,
    "BillingMode": "PAY_PER_REQUEST",
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": "GSI1PK", "AttributeType": "S"},
        {"AttributeName": "GSI1SK", "AttributeType": "S"},
    ],
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},
        {"AttributeName": "SK", "KeyType": "RANGE"},
    ],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": "GSI1",
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }
    ],
}
