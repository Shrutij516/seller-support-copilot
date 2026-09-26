import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from copilot_api.config import Settings, get_settings
from copilot_api.dynamo.table import TABLE_NAME

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


async def check_postgres(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def check_dynamodb(settings: Settings) -> None:
    def _describe_table() -> None:
        client = boto3.client(
            "dynamodb",
            region_name=settings.aws_region,
            endpoint_url=settings.dynamodb_endpoint_url,
            config=BotoConfig(
                connect_timeout=settings.readiness_timeout_seconds,
                read_timeout=settings.readiness_timeout_seconds,
                retries={"max_attempts": 0},
            ),
        )
        # Scoped to the one table the API uses, not a blanket ListTables permission.
        client.describe_table(TableName=TABLE_NAME)

    await asyncio.to_thread(_describe_table)


def get_db_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.db_engine
    return engine


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", responses={503: {"description": "One or more dependencies failed"}})
async def readyz(
    settings: Settings = Depends(get_settings),  # noqa: B008
    engine: AsyncEngine = Depends(get_db_engine),  # noqa: B008
) -> JSONResponse:
    checks: dict[str, Callable[[], Coroutine[Any, Any, None]]] = {
        "postgres": lambda: check_postgres(engine),
        "dynamodb": lambda: check_dynamodb(settings),
    }
    results = await asyncio.gather(
        *(
            asyncio.wait_for(check(), timeout=settings.readiness_timeout_seconds)
            for check in checks.values()
        ),
        return_exceptions=True,
    )
    statuses: dict[str, str] = {}
    for name, result in zip(checks, results, strict=True):
        if isinstance(result, BaseException):
            # Details go to logs only; the response names the dependency without leaking internals.
            logger.warning(
                "readiness check failed", extra={"dependency": name, "error": repr(result)}
            )
            statuses[name] = "fail"
        else:
            statuses[name] = "ok"
    failed = [name for name, status in statuses.items() if status != "ok"]
    body: dict[str, Any] = {"status": "fail" if failed else "ok", "checks": statuses}
    if failed:
        body["failed"] = failed
    return JSONResponse(body, status_code=503 if failed else 200)
