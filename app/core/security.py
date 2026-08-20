from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from passlib.context import CryptContext

from app.core.config import settings

# Argon2id per the Candidexa security spec: 19 MiB memory, t=2, p=1.
pwd_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

# Legacy scheme used before the Argon2id migration. Kept only so existing
# users can log in once and be transparently upgraded to an Argon2id hash.
legacy_pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def get_password_hash(password: str) -> str:
    return pwd_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verify a password against an Argon2id hash, falling back to the
    legacy sha256_crypt scheme for hashes created before the migration."""
    if not hashed_password:
        return False
    if hashed_password.startswith("$argon2"):
        try:
            return pwd_hasher.verify(hashed_password, plain_password)
        except VerifyMismatchError:
            return False
        except InvalidHashError:
            return False
    try:
        return legacy_pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def needs_rehash(hashed_password: Optional[str]) -> bool:
    """True when the stored hash is legacy (or used weak parameters) and
    should be replaced with a fresh Argon2id hash on the next successful login."""
    if not hashed_password:
        return False
    if not hashed_password.startswith("$argon2"):
        return True
    try:
        return pwd_hasher.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return True


def _create_token(
    subject: str,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str) -> str:
    return _create_token(
        subject, TOKEN_TYPE_ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject, TOKEN_TYPE_REFRESH, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> Dict[str, Any]:
    """Decode a JWT and enforce its type claim. Raises jwt.PyJWTError on any
    invalid token, including using a refresh token where an access token is
    required (and vice versa)."""
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
    return payload
