from __future__ import annotations

from fastapi import Request
from typing import Callable, Awaitable
from fastapi.responses import JSONResponse


class AppException(Exception):
    pass


class ServerError(AppException):
    """Internal Server error."""

    pass


class ServiceUnavailable(AppException):
    """Service unavailable temporarily"""

    def __init__(self, retry_after):
        self.retry_after = retry_after


class ReferenceNotFound(AppException):
    """Transaction not found with reference.
    Raised for the transaction verify endpoint
    """

    pass


class MaxRetriesError(AppException):
    """Maximum retries exceeded"""

    pass


class AuthenticationError(AppException):
    """User not authenticated."""

    pass


class AuthorizationError(AppException):
    """User not authorized"""

    pass


class UserExistsError(AppException):
    """User already exists"""

    def __init__(self, user_email: str):
        self.user_email = user_email


class UserNotFoundError(AppException):
    """User not found"""

    def __init__(self, user_email: str):
        self.user_email = user_email


class WalletCreditNotFoundError(AppException):
    """Wallet credit not found"""

    def __init__(self, id: str):
        self.id = id


class WalletCreditsNotFoundError(AppException):
    """Wallet credits not found"""


class InvalidOtpError(AppException):
    """Invalid otp received"""

    pass


class CredentialError(AppException):
    """wrong credentials provided"""

    pass


def create_exception_handler(
    status_code: int, initial_detail: dict
) -> Callable[[Request, AppException], Awaitable[JSONResponse]]:
    async def exception_handler(request: Request, exc: AppException):
        headers = None
        message: str = initial_detail.get("message")
        initial_detail["message"] = message.format(**exc.__dict__)

        if isinstance(exc, ServiceUnavailable):
            retry_after = exc.retry_after
            headers = {"x-retry-after": retry_after}

        return JSONResponse(content=initial_detail, status_code=status_code, headers=headers)

    return exception_handler
