from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session
from domain.req import TransactionCreateRequest
from domain.res import ApiResponse, TransactionData
from service.transaction_service import execute_create_transaction


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post(
    "",
    response_model=ApiResponse[TransactionData],
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    transaction: TransactionCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TransactionData]:
    created = await execute_create_transaction(transaction, session)
    return ApiResponse(
        data=TransactionData.model_validate(created),
        message="transaction created",
        request_id=getattr(request.state, "request_id", None),
    )
