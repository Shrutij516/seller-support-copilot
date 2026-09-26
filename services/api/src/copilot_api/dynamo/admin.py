"""Table creation/TTL setup, shared by `make dynamodb-init` and the integration test fixtures
that stand up an isolated table for tests. Not used by the running API itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from copilot_api.dynamo.table import TTL_ATTRIBUTE

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient


def ensure_table(client: DynamoDBClient, schema: dict[str, Any]) -> None:
    """Create the table described by `schema` and enable TTL, idempotently."""
    table_name = schema["TableName"]
    try:
        client.create_table(**schema)
        client.get_waiter("table_exists").wait(TableName=table_name)
    except client.exceptions.ResourceInUseException:
        pass

    ttl_status = client.describe_time_to_live(TableName=table_name)["TimeToLiveDescription"].get(
        "TimeToLiveStatus"
    )
    if ttl_status not in ("ENABLED", "ENABLING"):
        client.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
        )
