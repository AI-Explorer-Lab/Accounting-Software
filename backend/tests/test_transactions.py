from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

import controller.transaction_api as transaction_api
from constant.enums import TransactionType
from exceptions.business_exception import BusinessException
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


@pytest.mark.asyncio
async def test_list_transactions_supports_pagination_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_query = None

    async def fake_list_transactions(query, _session):
        nonlocal captured_query
        captured_query = query
        return [
            SimpleNamespace(
                id=7,
                amount=Decimal("88.00"),
                category="Food",
                description="Dinner",
                transaction_date=date(2026, 7, 14),
                transaction_type=TransactionType.EXPENSE,
            )
        ], 11

    monkeypatch.setattr(
        transaction_api,
        "execute_list_transactions",
        fake_list_transactions,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/transactions",
            params={
                "page": 2,
                "page_size": 5,
                "transaction_type": "expense",
                "category": "Food",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )

    assert response.status_code == 200
    assert captured_query is not None
    assert captured_query.page == 2
    assert captured_query.page_size == 5
    assert captured_query.transaction_type is TransactionType.EXPENSE
    assert captured_query.category == "Food"
    body = response.json()
    assert body["data"] == {
        "items": [
            {
                "id": 7,
                "amount": "88.00",
                "category": "Food",
                "description": "Dinner",
                "transaction_date": "2026-07-14",
                "transaction_type": "expense",
            }
        ],
        "total": 11,
        "page": 2,
        "page_size": 5,
    }


@pytest.mark.asyncio
async def test_list_transactions_returns_empty_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list_transactions(_query, _session):
        return [], 0

    monkeypatch.setattr(
        transaction_api,
        "execute_list_transactions",
        fake_list_transactions,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/transactions")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }


@pytest.mark.asyncio
async def test_list_transactions_rejects_reversed_date_range() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/transactions",
            params={"start_date": "2026-07-31", "end_date": "2026-07-01"},
        )

    assert response.status_code == 422
    assert response.json()["message"] == "start_date cannot be after end_date"


@pytest.mark.asyncio
async def test_delete_transaction_returns_deleted_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_id = None

    async def fake_delete_transaction(transaction_id, _session):
        nonlocal captured_id
        captured_id = transaction_id

    monkeypatch.setattr(
        transaction_api,
        "execute_delete_transaction",
        fake_delete_transaction,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/transactions/7")

    assert response.status_code == 200
    assert captured_id == 7
    assert response.json()["data"] == {"id": 7}


@pytest.mark.asyncio
async def test_delete_transaction_returns_404_when_record_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_delete_transaction(_transaction_id, _session):
        raise BusinessException("transaction not found", status_code=404)

    monkeypatch.setattr(
        transaction_api,
        "execute_delete_transaction",
        fake_delete_transaction,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/transactions/999")

    assert response.status_code == 404
    assert response.json()["message"] == "transaction not found"
