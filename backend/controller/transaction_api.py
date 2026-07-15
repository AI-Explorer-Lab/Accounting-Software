from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from constant.enums import TransactionType
from constant.values import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from database.session import get_session
from domain.req import TransactionCreateRequest, TransactionListRequest
from domain.res import (
    ApiResponse,
    TransactionData,
    TransactionDeleteData,
    TransactionPageData,
)
from exceptions.business_exception import BusinessException
from service.transaction_service import (
    execute_create_transaction,
    execute_delete_transaction,
    execute_list_transactions,
)


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=ApiResponse[TransactionPageData])
async def list_transactions(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    transaction_type: TransactionType | None = Query(default=None),
    category: str | None = Query(default=None, max_length=100),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TransactionPageData]:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise BusinessException("start_date cannot be after end_date", status_code=422)

    query = TransactionListRequest(
        page=page,
        page_size=page_size,
        transaction_type=transaction_type,
        category=category,
        start_date=start_date,
        end_date=end_date,
    )
    records, total = await execute_list_transactions(query, session)
    return ApiResponse(
        data=TransactionPageData(
            items=[TransactionData.model_validate(record) for record in records],
            total=total,
            page=page,
            page_size=page_size,
        ),
        message="transactions retrieved",
        request_id=getattr(request.state, "request_id", None),
    )


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


@router.delete("/{transaction_id}", response_model=ApiResponse[TransactionDeleteData])
async def delete_transaction(
    transaction_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TransactionDeleteData]:
    await execute_delete_transaction(transaction_id, session)
    return ApiResponse(
        data=TransactionDeleteData(id=transaction_id),
        message="transaction deleted",
        request_id=getattr(request.state, "request_id", None),
    )
