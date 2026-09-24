import asyncio
import logging
from typing import Any

import psycopg
import redis.asyncio as redis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from copilot_api.config import Settings, get_settings

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


async def check_postgres(settings: Settings) -> None:
    async with await psycopg.AsyncConnection.connect(
        settings.database_url, connect_timeout=max(1, int(settings.readiness_timeout_seconds))
    ) as conn:
        await conn.execute("SELECT 1")


async def check_redis(settings: Settings) -> None:
    client = redis.from_url(settings.redis_url, socket_timeout=settings.readiness_timeout_seconds)
    try:
        await client.ping()
    finally:
        await client.aclose()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", responses={503: {"description": "One or more dependencies failed"}})
async def readyz(settings: Settings = Depends(get_settings)) -> JSONResponse:  # noqa: B008
    checks = {"postgres": check_postgres, "redis": check_redis}
    results = await asyncio.gather(
        *(
            asyncio.wait_for(check(settings), timeout=settings.readiness_timeout_seconds)
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
