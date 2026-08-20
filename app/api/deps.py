from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import ValidationError
from supabase import Client

from app.db.session import get_supabase_client
from app.core.config import settings
from app.schemas.user import TokenPayload

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)

def get_db() -> Client:
    # Yielding a Supabase client instead of SQLAlchemy session
    return get_supabase_client()

def get_current_user(
    db: Client = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    
    # Query user from Supabase
    response = db.table("users").select("*").eq("id", token_data.sub).execute()
    users = response.data
    
    if not users:
        raise HTTPException(status_code=404, detail="User not found")
        
    user = users[0]
    if not user.get("is_active"):
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user
