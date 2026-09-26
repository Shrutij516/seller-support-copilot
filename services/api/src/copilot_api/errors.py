"""RFC 9457 (application/problem+json) error responses for every error path: our own
raised errors, FastAPI/Pydantic validation failures, routing 404s, and anything unhandled.
Never includes a stack trace or raw exception text in the response; those go to logs only.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from copilot_api.logging import request_id_var

PROBLEM_CONTENT_TYPE = "application/problem+json"

logger = logging.getLogger(__name__)


class ProblemError(Exception):
    """Raise this (or a factory below) anywhere a request should fail with a problem+json
    response. `detail` is safe to show a caller: never a stack trace, a SQL fragment, or
    anything else internal.
    """

    def __init__(
        self, status_code: int, title: str, detail: str | None = None, type_: str = "about:blank"
    ) -> None:
        super().__init__(detail or title)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.type = type_


def unauthorized(detail: str) -> ProblemError:
    return ProblemError(401, "Unauthorized", detail)


def forbidden(detail: str) -> ProblemError:
    return ProblemError(403, "Forbidden", detail)


def not_found(detail: str) -> ProblemError:
    return ProblemError(404, "Not Found", detail)


def conflict(detail: str) -> ProblemError:
    return ProblemError(409, "Conflict", detail)


def unprocessable(detail: str) -> ProblemError:
    return ProblemError(422, "Unprocessable Entity", detail)


def _problem_response(
    status_code: int, title: str, detail: str | None, type_: str = "about:blank"
) -> JSONResponse:
    body: dict[str, Any] = {"type": type_, "title": title, "status": status_code}
    if detail:
        body["detail"] = detail
    request_id = request_id_var.get()
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=status_code, media_type=PROBLEM_CONTENT_TYPE)


async def _handle_problem_error(request: Request, exc: ProblemError) -> JSONResponse:
    return _problem_response(exc.status_code, exc.title, exc.detail, exc.type)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "error"
    return _problem_response(exc.status_code, detail, None)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # exc.errors() already excludes the input's raw values by default in our schemas
    # (bounded strings, enums); still keep this to field+message only, nothing verbatim.
    problems = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return _problem_response(422, "Validation error", "; ".join(problems))


async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", exc_info=exc)
    return _problem_response(500, "Internal Server Error", None)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _handle_problem_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unhandled_exception)
