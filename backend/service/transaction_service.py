from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from constant.enums import ErrorCode
from domain.req import TransactionCreateRequest, TransactionListRequest
from exceptions.business_exception import BusinessException
from mapper.postgresql_transaction import TransactionEntity
from mapper.postgresql_transaction import create as create_transaction_record
from mapper.postgresql_transaction import delete_by_id
from mapper.postgresql_transaction import get_monthly_expenses_by_category
from mapper.postgresql_transaction import get_monthly_totals
from mapper.postgresql_transaction import list_records


async def execute_create_transaction(
    transaction: TransactionCreateRequest,
    session: AsyncSession,
) -> TransactionEntity:
    return await create_transaction_record(
        session,
        amount=transaction.amount,
        category=transaction.category,
        description=transaction.description,
        transaction_date=transaction.transaction_date,
        transaction_type=transaction.transaction_type,
    )


async def execute_list_transactions(
    query: TransactionListRequest,
    session: AsyncSession,
) -> tuple[list[TransactionEntity], int]:
    return await list_records(
        session,
        page=query.page,
        page_size=query.page_size,
        transaction_type=query.transaction_type,
        category=query.category.strip() if query.category else None,
        start_date=query.start_date,
        end_date=query.end_date,
        min_amount=query.min_amount,
        max_amount=query.max_amount,
    )


async def execute_monthly_statistics(
    year: int,
    month: int,
    session: AsyncSession,
) -> tuple[Decimal, Decimal, Decimal, int, list[tuple[str, Decimal, Decimal]]]:
    start_date = date(year, month, 1)
    end_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    income_total, expense_total, transaction_count = await get_monthly_totals(
        session,
        start_date=start_date,
        end_date=end_date,
    )
    category_totals = await get_monthly_expenses_by_category(
        session,
        start_date=start_date,
        end_date=end_date,
    )
    expense_by_category = [
        (
            category,
            amount,
            (amount * Decimal("100") / expense_total).quantize(Decimal("0.01")),
        )
        for category, amount in category_totals
    ] if expense_total else []
    return (
        income_total,
        expense_total,
        income_total - expense_total,
        transaction_count,
        expense_by_category,
    )


async def execute_delete_transaction(
    transaction_id: int,
    session: AsyncSession,
) -> None:
    deleted = await delete_by_id(session, transaction_id)
    if not deleted:
        raise BusinessException(
            "transaction not found",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
