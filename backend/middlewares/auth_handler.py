from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from constant.enums import ErrorCode
from exceptions.business_exception import BusinessException


class AuthenticationError(BusinessException):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(
            message,
            code=ErrorCode.AUTHENTICATION_ERROR,
            status_code=401,
        )


class AuthorizationError(BusinessException):
    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(
            message,
            code=ErrorCode.AUTHORIZATION_ERROR,
            status_code=403,
        )


def register_auth_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthenticationError)
    async def handle_authentication_error(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "message": exc.message,
                "code": exc.code.value,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(AuthorizationError)
    async def handle_authorization_error(
        request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "message": exc.message,
                "code": exc.code.value,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
