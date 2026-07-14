from sqlalchemy.ext.asyncio import AsyncSession

from domain.req import TransactionCreateRequest
from mapper.postgresql_transaction import TransactionEntity
from mapper.postgresql_transaction import create as create_transaction_record


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
