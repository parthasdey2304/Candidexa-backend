"""Core package for Candidexa Backend."""

from app.core.config import settings, get_settings
from app.core.security import (
    get_password_hash,
    verify_password,
    needs_rehash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.logging_middleware import LoggingMiddleware
from app.core.rate_limit import RateLimiter, init_rate_limiter, close_rate_limiter, get_rate_limiter
from app.core.ai_guard import (
    redact_pii,
    check_prompt_injection,
    validate_input,
    validate_input_size,
    PromptInjectionError,
    InputTooLargeError,
    MatchResult,
    GenerationResult,
    local_match_score,
    parse_match_response,
    template_cover_letter,
)
from app.core.headers import SecurityHeadersMiddleware, get_csp_header, get_permissions_policy
from app.core.errors import (
    AppError,
    NotFoundError,
    UnauthorizedError,
    ForbiddenError,
    ValidationError,
    RateLimitError,
    AIProviderError,
    register_exception_handlers,
    generate_error_id,
)

__all__ = [
    "settings",
    "get_settings",
    "get_password_hash",
    "verify_password",
    "needs_rehash",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "LoggingMiddleware",
    "RateLimiter",
    "init_rate_limiter",
    "close_rate_limiter",
    "get_rate_limiter",
    "redact_pii",
    "check_prompt_injection",
    "validate_input",
    "validate_input_size",
    "PromptInjectionError",
    "InputTooLargeError",
    "MatchResult",
    "GenerationResult",
    "local_match_score",
    "parse_match_response",
    "template_cover_letter",
    "SecurityHeadersMiddleware",
    "get_csp_header",
    "get_permissions_policy",
    "AppError",
    "NotFoundError",
    "UnauthorizedError",
    "ForbiddenError",
    "ValidationError",
    "RateLimitError",
    "AIProviderError",
    "register_exception_handlers",
    "generate_error_id",
]