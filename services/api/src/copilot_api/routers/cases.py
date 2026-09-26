import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.auth import require_seller
from copilot_api.deps import get_db_session
from copilot_api.errors import not_found
from copilot_api.models import SupportCase
from copilot_api.schemas import CaseListResponse, SupportCaseResponse

router = APIRouter(prefix="/v1", tags=["cases"])


@router.get("/cases", response_model=CaseListResponse)
async def list_cases(
    seller_id: uuid.UUID = Depends(require_seller),
    session: AsyncSession = Depends(get_db_session),
) -> CaseListResponse:
    stmt = (
        select(SupportCase)
        .where(SupportCase.seller_id == seller_id)
        .order_by(SupportCase.created_at.desc())
    )
    result = await session.execute(stmt)
    return CaseListResponse(
        items=[SupportCaseResponse.model_validate(case) for case in result.scalars().all()]
    )


@router.get("/cases/{case_id}", response_model=SupportCaseResponse)
async def get_case(
    case_id: uuid.UUID,
    seller_id: uuid.UUID = Depends(require_seller),
    session: AsyncSession = Depends(get_db_session),
) -> SupportCaseResponse:
    stmt = select(SupportCase).where(SupportCase.id == case_id, SupportCase.seller_id == seller_id)
    case = (await session.execute(stmt)).scalar_one_or_none()
    if case is None:
        raise not_found("case not found")
    return SupportCaseResponse.model_validate(case)
