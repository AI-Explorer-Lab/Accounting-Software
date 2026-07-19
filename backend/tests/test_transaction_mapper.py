from datetime import date
from decimal import Decimal

import pytest

from constant.enums import TransactionType
from mapper.postgresql_transaction import list_records


class _ScalarResult:
    def all(self):
        return []


class _Result:
    def scalar_one(self):
        return 0

    def scalars(self):
        return _ScalarResult()


class _RecordingSession:
    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


@pytest.mark.asyncio
async def test_list_records_combines_inclusive_amount_and_existing_filters() -> None:
    session = _RecordingSession()

    records, total = await list_records(
        session,
        page=2,
        page_size=5,
        transaction_type=TransactionType.EXPENSE,
        category="Food",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
        min_amount=Decimal("10.00"),
        max_amount=Decimal("20.00"),
    )

    assert (records, total) == ([], 0)
    assert len(session.statements) == 2
    for statement in session.statements:
        sql = str(statement)
        assert "transactions.amount >=" in sql
        assert "transactions.amount <=" in sql
        assert "transactions.transaction_type =" in sql
        assert "lower(transactions.category) LIKE lower" in sql
        assert "transactions.transaction_date >=" in sql
        assert "transactions.transaction_date <=" in sql
    assert session.statements[1]._offset_clause.value == 5
    assert session.statements[1]._limit_clause.value == 5
