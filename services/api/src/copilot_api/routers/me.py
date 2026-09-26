from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.auth import Principal, get_current_principal
from copilot_api.deps import get_db_session
from copilot_api.errors import forbidden
from copilot_api.models import Seller
from copilot_api.schemas import MeResponse

router = APIRouter(prefix="/v1", tags=["me"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MeResponse:
    if principal.seller_id is None:
        # An admin isn't necessarily also a seller; that's not an error, just nothing to
        # report under seller_id/email/display_name. Anyone else with no linked sellers row
        # (a seller-group token that was never provisioned) is the actual error case.
        if "admin" in principal.roles:
            return MeResponse(
                seller_id=None, email=None, display_name=None, roles=sorted(principal.roles)
            )
        raise forbidden("account not provisioned")

    seller = await session.get(Seller, principal.seller_id)
    if seller is None:
        raise forbidden("account not provisioned")

    return MeResponse(
        seller_id=seller.id,
        email=seller.email,
        display_name=seller.display_name,
        roles=sorted(principal.roles),
    )
