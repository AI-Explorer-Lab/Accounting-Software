from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Enum as SqlEnum, Numeric, String, Text
from sqlalchemy import case
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from constant.enums import TransactionType
from database.session import Base


class TransactionEntity(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(
        SqlEnum(
            TransactionType,
            name="transaction_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )


async def create(
    session: AsyncSession,
    *,
    amount: Decimal,
    category: str,
    description: str | None,
    transaction_date: date,
    transaction_type: TransactionType,
) -> TransactionEntity:
    transaction = TransactionEntity(
        amount=amount,
        category=category,
        description=description,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
    )
    session.add(transaction)
    await session.flush()
    await session.refresh(transaction)
    return transaction


async def list_records(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    transaction_type: TransactionType | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
) -> tuple[list[TransactionEntity], int]:
    filters = []
    if transaction_type is not None:
        filters.append(TransactionEntity.transaction_type == transaction_type)
    if category:
        filters.append(TransactionEntity.category.ilike(f"%{category}%"))
    if start_date is not None:
        filters.append(TransactionEntity.transaction_date >= start_date)
    if end_date is not None:
        filters.append(TransactionEntity.transaction_date <= end_date)
    if min_amount is not None:
        filters.append(TransactionEntity.amount >= min_amount)
    if max_amount is not None:
        filters.append(TransactionEntity.amount <= max_amount)

    total_result = await session.execute(
        select(func.count()).select_from(TransactionEntity).where(*filters)
    )
    total = int(total_result.scalar_one())

    records_result = await session.execute(
        select(TransactionEntity)
        .where(*filters)
        .order_by(TransactionEntity.transaction_date.desc(), TransactionEntity.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(records_result.scalars().all()), total


async def get_monthly_totals(
    session: AsyncSession,
    *,
    start_date: date,
    end_date: date,
) -> tuple[Decimal, Decimal, int]:
    result = await session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            TransactionEntity.transaction_type
                            == TransactionType.INCOME,
                            TransactionEntity.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            TransactionEntity.transaction_type
                            == TransactionType.EXPENSE,
                            TransactionEntity.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.count(TransactionEntity.id),
        ).where(
            TransactionEntity.transaction_date >= start_date,
            TransactionEntity.transaction_date < end_date,
        )
    )
    income_total, expense_total, transaction_count = result.one()
    return Decimal(income_total), Decimal(expense_total), int(transaction_count)


async def get_monthly_expenses_by_category(
    session: AsyncSession,
    *,
    start_date: date,
    end_date: date,
) -> list[tuple[str, Decimal]]:
    amount_total = func.sum(TransactionEntity.amount).label("amount_total")
    result = await session.execute(
        select(TransactionEntity.category, amount_total)
        .where(
            TransactionEntity.transaction_type == TransactionType.EXPENSE,
            TransactionEntity.transaction_date >= start_date,
            TransactionEntity.transaction_date < end_date,
        )
        .group_by(TransactionEntity.category)
        .order_by(amount_total.desc(), TransactionEntity.category.asc())
    )
    return [(category, Decimal(amount)) for category, amount in result.all()]


async def delete_by_id(session: AsyncSession, transaction_id: int) -> bool:
    result = await session.execute(
        select(TransactionEntity).where(TransactionEntity.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        return False

    await session.delete(transaction)
    await session.flush()
    return True
