from fastapi import APIRouter, Request

from config.config import settings
from constant.values import APP_VERSION
from domain.res import ApiResponse, HealthData


router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthData])
async def health(request: Request) -> ApiResponse[HealthData]:
    return ApiResponse(
        data=HealthData(
            status="ok",
            environment=str(settings.environment.name),
            version=APP_VERSION,
        ),
        request_id=getattr(request.state, "request_id", None),
    )
