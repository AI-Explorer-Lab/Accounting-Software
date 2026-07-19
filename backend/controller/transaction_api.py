from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from constant.enums import TransactionType
from constant.values import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from database.session import get_session
from domain.req import TransactionCreateRequest, TransactionListRequest
from domain.res import (
    ApiResponse,
    ExpenseCategoryData,
    MonthlyTransactionStatisticsData,
    TransactionData,
    TransactionDeleteData,
    TransactionPageData,
)
from exceptions.business_exception import BusinessException
from service.transaction_service import (
    execute_create_transaction,
    execute_delete_transaction,
    execute_list_transactions,
    execute_monthly_statistics,
)


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get(
    "/statistics/monthly",
    response_model=ApiResponse[MonthlyTransactionStatisticsData],
)
async def get_monthly_statistics(
    request: Request,
    month: str = Query(description="Month in YYYY-MM format"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MonthlyTransactionStatisticsData]:
    try:
        parsed_month = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise BusinessException(
            "month must be a valid month in YYYY-MM format",
            status_code=422,
        ) from exc
    if month != parsed_month.strftime("%Y-%m"):
        raise BusinessException(
            "month must be a valid month in YYYY-MM format",
            status_code=422,
        )

    income_total, expense_total, balance, transaction_count, expense_by_category = (
        await execute_monthly_statistics(
            parsed_month.year,
            parsed_month.month,
            session,
        )
    )
    return ApiResponse(
        data=MonthlyTransactionStatisticsData(
            month=month,
            income_total=income_total,
            expense_total=expense_total,
            balance=balance,
            transaction_count=transaction_count,
            expense_by_category=[
                ExpenseCategoryData(
                    category=category,
                    amount=amount,
                    percentage=percentage,
                )
                for category, amount, percentage in expense_by_category
            ],
        ),
        message="monthly transaction statistics retrieved",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("", response_model=ApiResponse[TransactionPageData])
async def list_transactions(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    transaction_type: TransactionType | None = Query(default=None),
    category: str | None = Query(default=None, max_length=100),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    min_amount: Decimal | None = Query(default=None, gt=0),
    max_amount: Decimal | None = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TransactionPageData]:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise BusinessException("start_date cannot be after end_date", status_code=422)
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise BusinessException("min_amount cannot be greater than max_amount", status_code=422)

    query = TransactionListRequest(
        page=page,
        page_size=page_size,
        transaction_type=transaction_type,
        category=category,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
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
