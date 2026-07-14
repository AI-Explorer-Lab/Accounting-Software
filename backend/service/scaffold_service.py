from domain.models import CurrentUser, UseCaseResult
from exceptions.business_exception import BusinessException


def validate_business(use_case_name: str) -> None:
    if not use_case_name.strip():
        raise BusinessException("Use-case name cannot be empty")


async def execute_use_case(
    use_case_name: str,
    current_user: CurrentUser,
) -> UseCaseResult:
    """Demonstrate orchestration without implementing accounting behavior."""
    validate_business(use_case_name)
    return UseCaseResult(
        name=use_case_name,
        status="scaffold-ready",
        actor=current_user.subject,
    )
