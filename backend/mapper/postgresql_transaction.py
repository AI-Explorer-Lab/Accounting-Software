from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Enum as SqlEnum, Numeric, String, Text
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
