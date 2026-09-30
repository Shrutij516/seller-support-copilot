"""Keyset (seek) pagination on (placed_at, id): no OFFSET, so no duplicates or gaps when
rows are inserted between page fetches, and no cost that grows with how deep a page is.
"""

import base64
import binascii
import json
import uuid
from datetime import datetime

from copilot_api.errors import unprocessable
from copilot_api.models import CaseStatus


def encode_orders_cursor(placed_at: datetime, order_id: uuid.UUID) -> str:
    payload = {"placed_at": placed_at.isoformat(), "id": str(order_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_orders_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["placed_at"]), uuid.UUID(payload["id"])
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise unprocessable("invalid cursor") from exc


def encode_admin_cases_cursor(status: CaseStatus, created_at: datetime, case_id: uuid.UUID) -> str:
    payload = {"status": status.value, "created_at": created_at.isoformat(), "id": str(case_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_admin_cases_cursor(cursor: str) -> tuple[CaseStatus, datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return (
            CaseStatus(payload["status"]),
            datetime.fromisoformat(payload["created_at"]),
            uuid.UUID(payload["id"]),
        )
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise unprocessable("invalid cursor") from exc
