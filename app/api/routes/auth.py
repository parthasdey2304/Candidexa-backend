from __future__ import annotations
from datetime import datetime, timezone, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, auth_rate_limit
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.crypto import blind_index
from app.core.config import settings
from app.db.models import User, RefreshToken

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_rate_limit)])
async def register(
    request: Request,
    email: str,
    password: str,
    full_name: str | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Register a new user using standard email and password."""
    # Check if user exists via blind index
    existing = await db.execute(
        select(User).where(User.email_hmac == blind_index(email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )

    # Hash password with Argon2id
    hashed_password = hash_password(password)

    # Create user
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hashed_password,
        auth_provider="email",
        is_verified=False,  # In production, send verification email
    )
    db.add(user)
    await db.flush()

    # Issue tokens
    access_token = create_access_token(str(user.id))
    refresh_token, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=exp))

    await db.commit()

    # Set CSRF token for this session
    request.state.csrf_token = secrets.token_urlsafe(32)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session),
):
    """OAuth2 compatible token login, get an access token for future requests."""
    # Find user by email blind index
    result = await db.execute(
        select(User).where(User.email_hmac == blind_index(form_data.username))
    )
    user = result.scalar_one_or_none()

    if user is None or user.auth_provider != "email":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")

    if not verify_password(form_data.password, user.hashed_password):
        # Increment failed attempts
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None

    # Issue tokens
    access_token = create_access_token(str(user.id))
    refresh_token, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=exp))

    await db.commit()

    # Set CSRF token for this session
    request.state.csrf_token = secrets.token_urlsafe(32)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh")
async def refresh_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db_session),
):
    """Rotate refresh token and issue new access token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_refresh_token")

    try:
        payload = decode_token(credentials.credentials, expected_type="refresh")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

    rt = await db.get(RefreshToken, payload["jti"])
    if rt is None or rt.revoked or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_token_invalid")

    # Revoke old token (rotation defeats token theft replay)
    rt.revoked = True
    user = await db.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_invalid")

    # Issue new tokens
    access_token = create_access_token(str(user.id))
    new_refresh_token, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=exp))

    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db_session),
):
    """Revoke refresh token (logout)."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_refresh_token")

    try:
        payload = decode_token(credentials.credentials, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

    rt = await db.get(RefreshToken, payload["jti"])
    if rt:
        rt.revoked = True
        await db.commit()

    return {"message": "Logged out successfully"}


@router.post("/google", dependencies=[Depends(auth_rate_limit)])
async def google_auth(
    request: Request,
    credential: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Verify Google OAuth token and issue our own custom JWT."""
    try:
        idinfo = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )

        if idinfo["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            raise ValueError("Wrong issuer.")

        email = idinfo["email"]
        full_name = idinfo.get("name", "")

        # Check if user exists via blind index
        result = await db.execute(
            select(User).where(User.email_hmac == blind_index(email))
        )
        user = result.scalar_one_or_none()

        if user is None:
            # Create user
            user = User(
                email=email,
                full_name=full_name,
                auth_provider="google",
                is_verified=True,  # Google already verified
            )
            db.add(user)
            await db.flush()
        elif user.auth_provider != "google":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already registered with email/password")

        # Issue tokens
        access_token = create_access_token(str(user.id))
        refresh_token, jti, exp = create_refresh_token(str(user.id))
        db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=exp))

        await db.commit()

        request.state.csrf_token = secrets.token_urlsafe(32)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Google token")