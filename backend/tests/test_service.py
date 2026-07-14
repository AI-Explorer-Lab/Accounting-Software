import pytest

from domain.models import CurrentUser
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
