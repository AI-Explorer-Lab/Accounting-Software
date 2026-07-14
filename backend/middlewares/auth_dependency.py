from collections.abc import Callable

from fastapi import Depends, Header

from domain.models import CurrentUser
from middlewares.auth_handler import AuthorizationError


async def get_current_user(
    x_user_id: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
) -> CurrentUser:
    """Temporary local identity until a real authentication provider is selected."""
    roles = tuple(role.strip() for role in (x_user_roles or "").split(",") if role.strip())
    return CurrentUser(subject=x_user_id or "local-user", roles=roles)


def require_roles(*required_roles: str) -> Callable[..., CurrentUser]:
    async def dependency(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if not set(required_roles).issubset(user.roles):
            raise AuthorizationError("Insufficient permissions")
        return user

    return dependency
