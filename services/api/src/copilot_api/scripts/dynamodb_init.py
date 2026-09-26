"""Create the "chat" table (idempotent). Run via `make dynamodb-init`.

Local dev only today, against DynamoDB Local; the same TABLE_SCHEMA is what the AWS runbook
will use to create the real table later.
"""

from copilot_api.config import get_settings
from copilot_api.dynamo.admin import ensure_table
from copilot_api.dynamo.client import create_dynamodb_client
from copilot_api.dynamo.table import TABLE_NAME, TABLE_SCHEMA, TTL_ATTRIBUTE


def main() -> None:
    client = create_dynamodb_client(get_settings())
    ensure_table(client, TABLE_SCHEMA)
    print(f"table {TABLE_NAME!r} ready, TTL enabled on {TTL_ATTRIBUTE!r}")


if __name__ == "__main__":
    main()
