import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from copilot_api.auth import require_role
from copilot_api.deps import get_db_session
from copilot_api.errors import conflict, not_found
from copilot_api.models import CaseStatus, SupportCase
from copilot_api.pagination import decode_admin_cases_cursor, encode_admin_cases_cursor
from copilot_api.schemas import AdminCaseListResponse, AdminCaseResponse, AdminCaseUpdateBody

router = APIRouter(
    prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))]
)

# Explicit allowed-transition table: anything not listed here (including "stay put" and
# skipping a step) is rejected with 409, not silently allowed.
ALLOWED_CASE_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.OPEN: frozenset({CaseStatus.IN_PROGRESS}),
    CaseStatus.IN_PROGRESS: frozenset({CaseStatus.RESOLVED}),
    CaseStatus.RESOLVED: frozenset(),
}


def _admin_case_response(case: SupportCase) -> AdminCaseResponse:
    return AdminCaseResponse(
        id=case.id,
        order_id=case.order_id,
        type=case.type,
        status=case.status,
        description=case.description,
        created_at=case.created_at,
        seller_display_name=case.seller.display_name,
    )


@router.get("/cases", response_model=AdminCaseListResponse)
async def admin_list_cases(
    session: AsyncSession = Depends(get_db_session),
    status: CaseStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> AdminCaseListResponse:
    # Default order is the work queue itself, not an accident of created_at: open cases
    # first, then in_progress, then resolved (case_status is a native Postgres enum declared
    # in exactly that order, so ORDER BY status sorts by queue priority, not alphabetically),
    # oldest first (FIFO) within each status, id as the final tiebreaker so the ordering is
    # strict and keyset pagination has something unique to seek from.
    stmt = (
        select(SupportCase)
        .options(selectinload(SupportCase.seller))
        .order_by(SupportCase.status.asc(), SupportCase.created_at.asc(), SupportCase.id.asc())
    )
    if status is not None:
        stmt = stmt.where(SupportCase.status == status)
    if cursor:
        cursor_status, cursor_created_at, cursor_id = decode_admin_cases_cursor(cursor)
        stmt = stmt.where(
            tuple_(SupportCase.status, SupportCase.created_at, SupportCase.id)
            > tuple_(cursor_status, cursor_created_at, cursor_id)
        )
    stmt = stmt.limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = (
        encode_admin_cases_cursor(page_rows[-1].status, page_rows[-1].created_at, page_rows[-1].id)
        if has_more
        else None
    )
    return AdminCaseListResponse(
        items=[_admin_case_response(case) for case in page_rows], next_cursor=next_cursor
    )


@router.patch("/cases/{case_id}", response_model=AdminCaseResponse)
async def admin_update_case(
    case_id: uuid.UUID,
    body: AdminCaseUpdateBody,
    session: AsyncSession = Depends(get_db_session),
) -> AdminCaseResponse:
    stmt = (
        select(SupportCase)
        .where(SupportCase.id == case_id)
        .options(selectinload(SupportCase.seller))
    )
    case = (await session.execute(stmt)).scalar_one_or_none()
    if case is None:
        raise not_found("case not found")

    allowed = ALLOWED_CASE_TRANSITIONS.get(case.status, frozenset())
    if body.status not in allowed:
        raise conflict(f"cannot transition case from {case.status.value} to {body.status.value}")

    case.status = body.status
    await session.flush()
    return _admin_case_response(case)
