from datetime import date
from decimal import Decimal

import pytest

import service.transaction_service as transaction_service
from domain.models import CurrentUser
from domain.req import TransactionListRequest
from exceptions.business_exception import BusinessException
from service.scaffold_service import execute_use_case, validate_business


@pytest.mark.asyncio
async def test_execute_use_case_returns_scaffold_result() -> None:
    result = await execute_use_case("architecture", CurrentUser(subject="tester"))
    assert result.status == "scaffold-ready"
    assert result.actor == "tester"


def test_validate_business_rejects_blank_name() -> None:
    with pytest.raises(BusinessException):
        validate_business(" ")


@pytest.mark.asyncio
async def test_list_transactions_normalizes_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_category = None

    async def fake_list_records(_session, **kwargs):
        nonlocal captured_category
        captured_category = kwargs["category"]
        return [], 0

    monkeypatch.setattr(transaction_service, "list_records", fake_list_records)
    result = await transaction_service.execute_list_transactions(
        TransactionListRequest(category="  Food  "),
        object(),
    )

    assert result == ([], 0)
    assert captured_category == "Food"


@pytest.mark.asyncio
async def test_list_transactions_passes_inclusive_amount_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs = None

    async def fake_list_records(_session, **kwargs):
        nonlocal captured_kwargs
        captured_kwargs = kwargs
        return [], 0

    monkeypatch.setattr(transaction_service, "list_records", fake_list_records)
    await transaction_service.execute_list_transactions(
        TransactionListRequest(min_amount=Decimal("10.00"), max_amount=Decimal("20.00")),
        object(),
    )

    assert captured_kwargs is not None
    assert captured_kwargs["min_amount"] == Decimal("10.00")
    assert captured_kwargs["max_amount"] == Decimal("20.00")


@pytest.mark.asyncio
async def test_delete_transaction_raises_404_when_record_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_delete_by_id(_session, _transaction_id):
        return False

    monkeypatch.setattr(transaction_service, "delete_by_id", fake_delete_by_id)

    with pytest.raises(BusinessException) as caught:
        await transaction_service.execute_delete_transaction(999, object())

    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_transaction_completes_when_record_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_id = None

    async def fake_delete_by_id(_session, transaction_id):
        nonlocal captured_id
        captured_id = transaction_id
        return True

    monkeypatch.setattr(transaction_service, "delete_by_id", fake_delete_by_id)

    await transaction_service.execute_delete_transaction(7, object())

    assert captured_id == 7


@pytest.mark.asyncio
async def test_monthly_statistics_calculates_boundaries_and_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_dates = None

    async def fake_get_monthly_totals(_session, **kwargs):
        nonlocal captured_dates
        captured_dates = (kwargs["start_date"], kwargs["end_date"])
        return Decimal("500.00"), Decimal("125.50"), 3

    async def fake_get_monthly_expenses_by_category(_session, **_kwargs):
        return [("Food", Decimal("100.00")), ("Travel", Decimal("25.50"))]

    monkeypatch.setattr(
        transaction_service,
        "get_monthly_totals",
        fake_get_monthly_totals,
    )
    monkeypatch.setattr(
        transaction_service,
        "get_monthly_expenses_by_category",
        fake_get_monthly_expenses_by_category,
    )
    result = await transaction_service.execute_monthly_statistics(2026, 12, object())

    assert captured_dates == (date(2026, 12, 1), date(2027, 1, 1))
    assert result == (
        Decimal("500.00"),
        Decimal("125.50"),
        Decimal("374.50"),
        3,
        [
            ("Food", Decimal("100.00"), Decimal("79.68")),
            ("Travel", Decimal("25.50"), Decimal("20.32")),
        ],
    )


@pytest.mark.asyncio
async def test_monthly_statistics_has_no_categories_when_expenses_are_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_monthly_totals(_session, **_kwargs):
        return Decimal("10.00"), Decimal("0"), 1

    async def fake_get_monthly_expenses_by_category(_session, **_kwargs):
        return []

    monkeypatch.setattr(transaction_service, "get_monthly_totals", fake_get_monthly_totals)
    monkeypatch.setattr(
        transaction_service,
        "get_monthly_expenses_by_category",
        fake_get_monthly_expenses_by_category,
    )

    result = await transaction_service.execute_monthly_statistics(2026, 7, object())
    assert result[-1] == []
