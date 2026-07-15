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
