"""Global exception handlers for FastAPI.

Provides consistent error responses without leaking sensitive information.
"""

import logging
import uuid
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

logger = logging.getLogger("error_handlers")


class AppError(Exception):
    """Base application error with user-safe message."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_ERROR",
        details: Dict[str, Any] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, resource: str = "Resource"):
        super().__init__(
            f"{resource} not found",
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            {"resource": resource},
        )


class UnauthorizedError(AppError):
    """Authentication required."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message,
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
        )


class ForbiddenError(AppError):
    """Access denied."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message,
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
        )


class ValidationError(AppError):
    """Input validation failed."""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            details or {},
        )


class RateLimitError(AppError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(
            message,
            status.HTTP_429_TOO_MANY_REQUESTS,
            "RATE_LIMITED",
            {"retry_after": retry_after},
        )


class AIProviderError(AppError):
    """AI provider error."""

    def __init__(self, message: str = "AI service temporarily unavailable"):
        super().__init__(
            message,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_PROVIDER_ERROR",
        )


def generate_error_id() -> str:
    """Generate a unique error ID for tracking."""
    return str(uuid.uuid4())[:8]


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        error_id = generate_error_id()
        logger.warning(
            "Application error: %s | id=%s path=%s method=%s",
            exc.error_code,
            error_id,
            request.url.path,
            request.method,
            extra={"error_id": error_id, "error_code": exc.error_code, "details": exc.details},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                    "error_id": error_id,
                }
            },
            headers={"X-Error-ID": error_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        error_id = generate_error_id()
        logger.warning(
            "HTTP error: %d | id=%s path=%s method=%s",
            exc.status_code,
            error_id,
            request.url.path,
            request.method,
            extra={"error_id": error_id, "status_code": exc.status_code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": exc.detail,
                    "error_id": error_id,
                }
            },
            headers={"X-Error-ID": error_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        error_id = generate_error_id()
        logger.warning(
            "Validation error | id=%s path=%s method=%s errors=%s",
            error_id,
            request.url.path,
            request.method,
            exc.errors(),
            extra={"error_id": error_id, "validation_errors": exc.errors()},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
                    "error_id": error_id,
                }
            },
            headers={"X-Error-ID": error_id},
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        error_id = generate_error_id()
        logger.warning(
            "Pydantic validation error | id=%s path=%s method=%s",
            error_id,
            request.url.path,
            request.method,
            extra={"error_id": error_id},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Data validation failed",
                    "error_id": error_id,
                }
            },
            headers={"X-Error-ID": error_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        error_id = generate_error_id()
        # Log full traceback server-side only
        logger.exception(
            "Unhandled exception | id=%s path=%s method=%s",
            error_id,
            request.url.path,
            request.method,
            extra={"error_id": error_id},
        )

        # In production, return generic message
        if settings.is_production:
            message = "An internal error occurred. Please try again later."
        else:
            message = f"{type(exc).__name__}: {str(exc)}"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": message,
                    "error_id": error_id,
                }
            },
            headers={"X-Error-ID": error_id},
        )