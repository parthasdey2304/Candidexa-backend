from __future__ import annotations
from datetime import datetime, timezone
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import User, RefreshToken
from app.core.security import decode_token
from app.core.rate_limit import rate_limit, ip_key
from app.core.config import settings

bearer = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncSession:
    async for s in get_db():
        yield s


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    # Rate-limit auth'd endpoints per IP first (cheap gate)
    await rate_limit(ip_key(request, "api"), settings.RATE_LIMIT_API_PER_MIN)

    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer_token")

    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token")

    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_inactive_or_missing")
    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "email_not_verified")
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_423_LOCKED, "account_temporarily_locked")
    return user


async def get_current_user_strict(
    request: Request,
    user: User = Depends(get_current_user),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> User:
    """Use on state-changing routes. Requires CSRF token matching the one bound to the session."""
    expected = getattr(request.state, "csrf_token", None)
    if not expected or not x_csrf_token or x_csrf_token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid_csrf_token")
    return user


def require_owner(resource_user_id_attr: str = "user_id"):
    """Object-level authorization: ensure resource belongs to current user."""
    from fastapi import Request as _R
    async def _dep(request: _R, user: User = Depends(get_current_user)):
        # resource is attached to request.state by the route after fetch
        resource = getattr(request.state, "resource", None)
        if resource is None or getattr(resource, resource_user_id_attr) != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "resource_not_found")
        return user
    return _dep


# Optional dependency - auth-aware refresh-token rotation
async def rotate_refresh_token(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db_session),
) -> tuple[User, str]:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_refresh_token")
    payload = decode_token(creds.credentials, expected_type="refresh")
    rt = await db.get(RefreshToken, payload["jti"])
    if rt is None or rt.revoked or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh_token_invalid")
    # Revoke old token (rotation defeats token theft replay)
    rt.revoked = True
    user = await db.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_invalid")
    return user, payload["jti"]


# Shared: pre-auth rate limit for /auth/login, /auth/register
async def auth_rate_limit(request: Request):
    await rate_limit(ip_key(request, "auth"), settings.RATE_LIMIT_AUTH_PER_MIN)