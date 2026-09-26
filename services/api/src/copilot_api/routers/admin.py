import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.auth import require_role
from copilot_api.deps import get_db_session
from copilot_api.errors import conflict, not_found
from copilot_api.models import CaseStatus, SupportCase
from copilot_api.schemas import AdminCaseUpdateBody, CaseListResponse, SupportCaseResponse

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


@router.get("/cases", response_model=CaseListResponse)
async def admin_list_cases(
    session: AsyncSession = Depends(get_db_session),
    status: CaseStatus | None = Query(default=None),
) -> CaseListResponse:
    stmt = select(SupportCase).order_by(SupportCase.created_at.desc())
    if status is not None:
        stmt = stmt.where(SupportCase.status == status)
    result = await session.execute(stmt)
    return CaseListResponse(
        items=[SupportCaseResponse.model_validate(case) for case in result.scalars().all()]
    )


@router.patch("/cases/{case_id}", response_model=SupportCaseResponse)
async def admin_update_case(
    case_id: uuid.UUID,
    body: AdminCaseUpdateBody,
    session: AsyncSession = Depends(get_db_session),
) -> SupportCaseResponse:
    case = await session.get(SupportCase, case_id)
    if case is None:
        raise not_found("case not found")

    allowed = ALLOWED_CASE_TRANSITIONS.get(case.status, frozenset())
    if body.status not in allowed:
        raise conflict(f"cannot transition case from {case.status.value} to {body.status.value}")

    case.status = body.status
    await session.commit()
    await session.refresh(case)
    return SupportCaseResponse.model_validate(case)
