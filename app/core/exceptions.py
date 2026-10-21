from typing import Any, List, Optional
from datetime import datetime, timezone
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger("desidhar.exceptions")


class AppException(Exception):
    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[List[Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or []


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[List[Any]] = None):
        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request", error_code: str = "BAD_REQUEST", details: Optional[List[Any]] = None):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized", details: Optional[List[Any]] = None):
        super().__init__(
            message=message,
            error_code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden", error_code: str = "FORBIDDEN", details: Optional[List[Any]] = None):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict", error_code: str = "RESOURCE_CONFLICT", details: Optional[List[Any]] = None):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class TokenReuseDetectedException(AppException):
    def __init__(self, message: str = "Security Alert: Refresh token reuse detected. All sessions revoked."):
        super().__init__(
            message=message,
            error_code="TOKEN_REUSE_DETECTED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=[],
        )


class StockUnavailableException(AppException):
    def __init__(self, message: str = "Requested quantity exceeds available stock", details: Optional[List[Any]] = None):
        super().__init__(
            message=message,
            error_code="STOCK_UNAVAILABLE",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class PaymentGatewayException(AppException):
    def __init__(self, message: str = "Payment gateway operation failed", details: Optional[List[Any]] = None):
        super().__init__(
            message=message,
            error_code="PAYMENT_GATEWAY_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
        )


def format_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[List[Any]] = None,
    path: Optional[str] = None,
) -> dict:
    return {
        "status": status_code,
        "error_code": error_code,
        "message": message,
        "details": details or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "path": path,
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(f"AppException [{exc.error_code}]: {exc.message} on {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            path=request.url.path,
        ),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        loc = " -> ".join([str(x) for x in err.get("loc", [])])
        details.append({
            "field": loc,
            "message": err.get("msg"),
            "type": err.get("type"),
        })
    logger.info(f"Validation error on {request.url.path}: {details}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=format_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            message="Input validation failed",
            details=details,
            path=request.url.path,
        ),
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error(f"Database error on {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=format_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DATABASE_ERROR",
            message="A database error occurred while processing the request",
            details=[],
            path=request.url.path,
        ),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.critical(f"Unhandled exception on {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=format_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred",
            details=[],
            path=request.url.path,
        ),
    )
