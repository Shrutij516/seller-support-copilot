import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.auth import require_seller
from copilot_api.deps import get_db_session
from copilot_api.models import Listing
from copilot_api.schemas import ListingResponse

router = APIRouter(prefix="/v1", tags=["listings"])


@router.get("/listings", response_model=list[ListingResponse])
async def list_listings(
    seller_id: uuid.UUID = Depends(require_seller),
    session: AsyncSession = Depends(get_db_session),
) -> list[ListingResponse]:
    stmt = select(Listing).where(Listing.seller_id == seller_id).order_by(Listing.created_at.desc())
    result = await session.execute(stmt)
    return [ListingResponse.model_validate(listing) for listing in result.scalars().all()]
