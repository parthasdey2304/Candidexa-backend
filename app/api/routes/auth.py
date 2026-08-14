from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.db.models import User
from app.api.deps import get_db
from app.core import security
from app.core.config import settings
from app.schemas.user import UserCreate, User as UserSchema, Token, GoogleTokenRequest

router = APIRouter()

@router.post("/signup", response_model=UserSchema)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user using standard email and password.
    """
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    user = User(
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        full_name=user_in.full_name,
        auth_provider="email"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or user.auth_provider != "email":
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    return {
        "access_token": security.create_access_token(user.id),
        "token_type": "bearer",
    }

@router.post("/google", response_model=Token)
def google_auth(request_data: GoogleTokenRequest, db: Session = Depends(get_db)):
    """
    Verify Google OAuth token and issue our own custom JWT.
    """
    try:
        # Verify the token with Google
        idinfo = id_token.verify_oauth2_token(
            request_data.credential, 
            google_requests.Request(), 
            settings.GOOGLE_CLIENT_ID
        )

        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')

        email = idinfo['email']
        full_name = idinfo.get('name', '')

        # Check if user exists
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            # Create user if they don't exist
            user = User(
                email=email,
                full_name=full_name,
                auth_provider="google"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif user.auth_provider != "google":
            # Prevent Google login if they signed up with password originally
            raise HTTPException(status_code=400, detail="User already registered with email/password")

        # Issue custom JWT
        return {
            "access_token": security.create_access_token(user.id),
            "token_type": "bearer",
        }

    except ValueError:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid Google token")
