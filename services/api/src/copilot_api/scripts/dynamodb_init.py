"""Create the "chat" table (idempotent). Run via `make dynamodb-init`.

Local dev only today, against DynamoDB Local; the same TABLE_SCHEMA is what the AWS runbook
will use to create the real table later.
"""

from copilot_api.config import get_settings
from copilot_api.dynamo.client import create_dynamodb_client
from copilot_api.dynamo.table import TABLE_NAME, TABLE_SCHEMA, TTL_ATTRIBUTE


def main() -> None:
    settings = get_settings()
    client = create_dynamodb_client(settings)

    try:
        client.create_table(**TABLE_SCHEMA)
        client.get_waiter("table_exists").wait(TableName=TABLE_NAME)
        print(f"created table {TABLE_NAME!r}")
    except client.exceptions.ResourceInUseException:
        print(f"table {TABLE_NAME!r} already exists, skipping create")

    ttl_status = client.describe_time_to_live(TableName=TABLE_NAME)["TimeToLiveDescription"].get(
        "TimeToLiveStatus"
    )
    if ttl_status in ("ENABLED", "ENABLING"):
        print(f"TTL already enabled on {TABLE_NAME!r}.{TTL_ATTRIBUTE}, skipping")
    else:
        client.update_time_to_live(
            TableName=TABLE_NAME,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
        )
        print(f"TTL enabled on {TABLE_NAME!r}.{TTL_ATTRIBUTE}")


if __name__ == "__main__":
    main()
