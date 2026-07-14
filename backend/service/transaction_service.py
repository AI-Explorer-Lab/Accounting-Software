from sqlalchemy.ext.asyncio import AsyncSession

from constant.enums import ErrorCode
from domain.req import TransactionCreateRequest, TransactionListRequest
from exceptions.business_exception import BusinessException
from mapper.postgresql_transaction import TransactionEntity
from mapper.postgresql_transaction import create as create_transaction_record
from mapper.postgresql_transaction import delete_by_id
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
