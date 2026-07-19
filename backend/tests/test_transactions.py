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
                "min_amount": "88.00",
                "max_amount": "100.00",
            },
        )

    assert response.status_code == 200
    assert captured_query is not None
    assert captured_query.page == 2
    assert captured_query.page_size == 5
    assert captured_query.transaction_type is TransactionType.EXPENSE
    assert captured_query.category == "Food"
    assert captured_query.min_amount == Decimal("88.00")
    assert captured_query.max_amount == Decimal("100.00")
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
@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"min_amount": "0"}, "greater_than"),
        ({"min_amount": "-1"}, "greater_than"),
        ({"max_amount": "not-a-number"}, "decimal_parsing"),
        (
            {"min_amount": "20.00", "max_amount": "10.00"},
            "min_amount cannot be greater than max_amount",
        ),
    ],
)
async def test_list_transactions_rejects_invalid_amount_range(
    params: dict[str, str],
    message: str,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/transactions", params=params)

    assert response.status_code == 422
    assert message in response.text


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


@pytest.mark.asyncio
async def test_monthly_statistics_returns_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_monthly_statistics(year, month, _session):
        assert (year, month) == (2026, 7)
        return (
            Decimal("1000.00"), Decimal("250.25"), Decimal("749.75"), 4,
            [
                ("Food", Decimal("200.00"), Decimal("79.92")),
                ("Travel", Decimal("50.25"), Decimal("20.08")),
            ],
        )

    monkeypatch.setattr(
        transaction_api,
        "execute_monthly_statistics",
        fake_monthly_statistics,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/transactions/statistics/monthly",
            params={"month": "2026-07"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "month": "2026-07",
        "income_total": "1000.00",
        "expense_total": "250.25",
        "balance": "749.75",
        "transaction_count": 4,
        "expense_by_category": [
            {"category": "Food", "amount": "200.00", "percentage": "79.92"},
            {"category": "Travel", "amount": "50.25", "percentage": "20.08"},
        ],
    }


@pytest.mark.asyncio
async def test_monthly_statistics_returns_zero_for_empty_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_monthly_statistics(_year, _month, _session):
        return Decimal("0"), Decimal("0"), Decimal("0"), 0, []

    monkeypatch.setattr(
        transaction_api,
        "execute_monthly_statistics",
        fake_monthly_statistics,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/transactions/statistics/monthly",
            params={"month": "2025-01"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "month": "2025-01",
        "income_total": "0",
        "expense_total": "0",
        "balance": "0",
        "transaction_count": 0,
        "expense_by_category": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("month", ["2026-7", "2026-13", "July-2026", "2026-07-01"])
async def test_monthly_statistics_rejects_invalid_month(month: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/transactions/statistics/monthly",
            params={"month": month},
        )

    assert response.status_code == 422
    assert response.json()["message"] == "month must be a valid month in YYYY-MM format"
