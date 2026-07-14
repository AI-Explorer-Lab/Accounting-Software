from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

import controller.transaction_api as transaction_api
from constant.enums import TransactionType
from main import app


async def _fake_create_transaction(transaction, _session):
    return SimpleNamespace(
        id=1,
        amount=transaction.amount,
        category=transaction.category,
        description=transaction.description,
        transaction_date=transaction.transaction_date,
        transaction_type=transaction.transaction_type,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("transaction_type", ["income", "expense"])
async def test_create_transaction_supports_income_and_expense(
    monkeypatch: pytest.MonkeyPatch,
    transaction_type: str,
) -> None:
    monkeypatch.setattr(
        transaction_api,
        "execute_create_transaction",
        _fake_create_transaction,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/transactions",
            json={
                "amount": "125.50",
                "category": "Salary" if transaction_type == "income" else "Food",
                "description": "test transaction",
                "transaction_date": "2026-07-14",
                "transaction_type": transaction_type,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {
        "id": 1,
        "amount": "125.50",
        "category": "Salary" if transaction_type == "income" else "Food",
        "description": "test transaction",
        "transaction_date": "2026-07-14",
        "transaction_type": transaction_type,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [None, 0, -1])
async def test_create_transaction_rejects_invalid_amount(amount: object) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/transactions",
            json={
                "amount": amount,
                "category": "Food",
                "transaction_date": "2026-07-14",
                "transaction_type": "expense",
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_transaction_rejects_unknown_type() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/transactions",
            json={
                "amount": "10.00",
                "category": "Food",
                "transaction_date": "2026-07-14",
                "transaction_type": "transfer",
            },
        )

    assert response.status_code == 422


def test_transaction_entity_contract() -> None:
    from mapper.postgresql_transaction import TransactionEntity

    transaction = TransactionEntity(
        amount=Decimal("10.00"),
        category="Food",
        description=None,
        transaction_date=date(2026, 7, 14),
        transaction_type=TransactionType.EXPENSE,
    )

    assert transaction.__tablename__ == "transactions"
    assert transaction.transaction_type is TransactionType.EXPENSE
