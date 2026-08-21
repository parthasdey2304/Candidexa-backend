from __future__ import annotations
import base64
import hmac
import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.low_level import Type
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from jose import jwt, JWTError

from app.core.config import settings

# Argon2id - memory-hard, side-channel resistant, OWASP-recommended.
_argon2 = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,   # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


# ---------- Passwords ----------
def get_password_hash(plain: str) -> str:
    return hash_password(plain)

def hash_password(plain: str) -> str:
    if not plain or len(plain) < 8:
        raise ValueError("Password must be at least 8 characters")
    return _argon2.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _argon2.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _argon2.check_needs_rehash(hashed)


# ---------- JWT ----------
def _encode_key() -> tuple[Any, str]:
    if settings.JWT_ALGORITHM == "RS256":
        if not settings.JWT_PRIVATE_KEY:
            raise RuntimeError("RS256 selected but JWT_PRIVATE_KEY not set")
        return settings.JWT_PRIVATE_KEY, "RS256"
    return settings.JWT_SECRET, "HS256"


def _decode_key() -> tuple[Any, str]:
    if settings.JWT_ALGORITHM == "RS256":
        if not settings.JWT_PUBLIC_KEY:
            raise RuntimeError("RS256 selected but JWT_PUBLIC_KEY not set")
        return settings.JWT_PUBLIC_KEY, "RS256"
    return settings.JWT_SECRET, "HS256"


def create_access_token(sub: str, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "jti": jti,
        "type": "access",
        **(extra or {}),
    }
    key, alg = _encode_key()
    return jwt.encode(payload, key, algorithm=alg)


def create_refresh_token(sub: str) -> tuple[str, str, datetime]:
    """Returns (token, jti, expiry) - caller must persist jti in DB."""
    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(32)
    exp = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "type": "refresh",
    }
    key, alg = _encode_key()
    return jwt.encode(payload, key, algorithm=alg), jti, exp


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> dict:
    key, alg = _decode_key()
    try:
        payload = jwt.decode(token, key, algorithms=[alg])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
    if payload.get("type") != expected_type:
        raise ValueError(f"Expected {expected_type} token, got {payload.get('type')}")
    if "jti" not in payload or "sub" not in payload:
        raise ValueError("Malformed token claims")
    return payload


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())