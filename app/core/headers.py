"""Security headers middleware for FastAPI.

Provides HSTS, CSP, X-Frame-Options, X-Content-Type-Options,
Referrer-Policy, and other security headers.
"""

from typing import List, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    def __init__(
        self,
        app,
        hsts_max_age: int = 31536000,
        include_subdomains: bool = True,
        preload: bool = True,
        csp: Optional[str] = None,
        frame_options: str = "DENY",
        content_type_options: str = "nosniff",
        referrer_policy: str = "strict-origin-when-cross-origin",
        permissions_policy: Optional[str] = None,
    ):
        super().__init__(app)
        self.hsts_max_age = hsts_max_age
        self.include_subdomains = include_subdomains
        self.preload = preload
        self.csp = csp
        self.frame_options = frame_options
        self.content_type_options = content_type_options
        self.referrer_policy = referrer_policy
        self.permissions_policy = permissions_policy

    def _build_hsts_header(self) -> str:
        parts = [f"max-age={self.hsts_max_age}"]
        if self.include_subdomains:
            parts.append("includeSubDomains")
        if self.preload:
            parts.append("preload")
        return "; ".join(parts)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # HSTS - only in production with HTTPS
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = self._build_hsts_header()

        # Frame options
        response.headers["X-Frame-Options"] = self.frame_options

        # Content type options
        response.headers["X-Content-Type-Options"] = self.content_type_options

        # Referrer policy
        response.headers["Referrer-Policy"] = self.referrer_policy

        # CSP
        if self.csp:
            response.headers["Content-Security-Policy"] = self.csp

        # Permissions policy
        if self.permissions_policy:
            response.headers["Permissions-Policy"] = self.permissions_policy

        # Additional security headers
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        return response


def get_csp_header() -> str:
    """Generate a restrictive Content-Security-Policy header.
    
    Adjust based on your frontend requirements.
    """
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )


def get_permissions_policy() -> str:
    """Generate a Permissions-Policy header."""
    return (
        "accelerometer=(), "
        "camera=(), "
        "geolocation=(), "
        "gyroscope=(), "
        "magnetometer=(), "
        "microphone=(), "
        "payment=(), "
        "usb=(), "
        "interest-cohort=()"
    )