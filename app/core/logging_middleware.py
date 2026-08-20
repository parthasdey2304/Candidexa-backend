"""Structured request logging middleware with PII redaction."""

import json
import logging
import re
import time
from typing import Any, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


# Sensitive headers/params to redact
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "jwt",
    "credential",
}

# Patterns for PII in request body/URL
PII_PATTERNS = [
    (re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\+?\d[\d\s-]{8,13}\d"), "[REDACTED_PHONE]"),
    (re.compile(r"Bearer\s+[\w\-._~+/]+=*"), "Bearer [REDACTED]"),
]


def redact_sensitive(data: Any) -> Any:
    """Recursively redact sensitive keys and PII from data structures."""
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(value)
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive(item) for item in data]
    elif isinstance(data, str):
        result = data
        for pattern, replacement in PII_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    return data


# Configure structured JSON logger
logger = logging.getLogger("candidexa.requests")
logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

# Console handler with JSON formatting
console_handler = logging.StreamHandler()
console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "name", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info",
            }:
                log_data[key] = value
        return json.dumps(log_data, default=str)


console_handler.setFormatter(JSONFormatter())
logger.addHandler(console_handler)

# Prevent propagation to root logger to avoid duplicate logs
logger.propagate = False


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log requests with structured JSON output and PII redaction."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()

        # Capture request info (redacted)
        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        url_path = str(request.url.path)
        query_params = redact_sensitive(dict(request.query_params))

        # Process request
        response = await call_next(request)

        process_time_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        # Log structured request info
        log_extra = {
            "client_ip": client_ip,
            "method": method,
            "path": url_path,
            "query_params": query_params,
            "status_code": status_code,
            "process_time_ms": round(process_time_ms, 2),
        }

        # Add request ID if available
        if hasattr(request.state, "request_id"):
            log_extra["request_id"] = request.state.request_id

        # Log level based on status code
        if status_code >= 500:
            logger.error("Request failed", extra=log_extra)
        elif status_code >= 400:
            logger.warning("Request error", extra=log_extra)
        else:
            logger.info("Request completed", extra=log_extra)

        return response
