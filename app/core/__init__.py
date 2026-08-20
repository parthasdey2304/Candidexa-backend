"""Core package for Candidexa Backend."""

from app.core.config import settings, get_settings
from app.core.security import (
    get_password_hash,
    verify_password,
    needs_rehash,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    constant_time_eq,
)
from app.core.crypto import encrypt_field, decrypt_field, blind_index, hash_sha256
from app.core.logging_middleware import RequestIdMiddleware
from app.core.rate_limit import rate_limit, ip_key, user_key
from app.core.ai_guard import (
    enforce_ai_limits,
    record_ai_usage,
    call_with_timeout,
    breakers,
    CircuitBreaker,
    ServiceUnavailableError,
)
from app.core.headers import SecurityHeadersMiddleware
from app.core.errors import (
    ServiceUnavailableError,
    register_exception_handlers,
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
    "hash_password",
    "constant_time_eq",
    "encrypt_field",
    "decrypt_field",
    "blind_index",
    "hash_sha256",
    "RequestIdMiddleware",
    "rate_limit",
    "ip_key",
    "user_key",
    "enforce_ai_limits",
    "record_ai_usage",
    "call_with_timeout",
    "breakers",
    "CircuitBreaker",
    "ServiceUnavailableError",
    "SecurityHeadersMiddleware",
    "register_exception_handlers",
]