from fastapi import APIRouter, Depends, Request

from domain.models import CurrentUser
from domain.res import ApiResponse
from middlewares.auth_dependency import get_current_user
from service.scaffold_service import execute_use_case


router = APIRouter(prefix="/scaffold", tags=["scaffold"])


@router.get("", response_model=ApiResponse[dict[str, str]])
async def scaffold_status(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, str]]:
    result = await execute_use_case("architecture", current_user)
    return ApiResponse(
        data={"name": result.name, "status": result.status, "actor": result.actor},
        request_id=getattr(request.state, "request_id", None),
    )
