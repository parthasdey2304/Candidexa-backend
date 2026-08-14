from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from supabase import Client

from app.api.deps import get_db
from app.core import security
from app.core.config import settings
from app.schemas.user import UserCreate, User as UserSchema, Token, GoogleTokenRequest

router = APIRouter()

@router.post("/signup", response_model=UserSchema)
def signup(user_in: UserCreate, db: Client = Depends(get_db)):
    """
    Register a new user using standard email and password.
    """
    # Check if user exists
    res = db.table("users").select("*").eq("email", user_in.email).execute()
    if res.data:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    
    # Hash password
    # The Supabase trigger we added will also hash passwords, but it expects plain text.
    # We should let the DB trigger do it if we configured it that way, or we can do it here.
    # Since our Python logic expects to verify it, we should hash it here.
    hashed_password = security.get_password_hash(user_in.password)
    
    new_user_data = {
        "email": user_in.email,
        "hashed_password": hashed_password,
        "full_name": user_in.full_name,
        "auth_provider": "email"
    }
    
    insert_res = db.table("users").insert(new_user_data).execute()
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Failed to create user")
        
    return insert_res.data[0]

@router.post("/login", response_model=Token)
def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Client = Depends(get_db)
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    res = db.table("users").select("*").eq("email", form_data.username).execute()
    users = res.data
    
    if not users or users[0].get("auth_provider") != "email":
        raise HTTPException(status_code=400, detail="Incorrect email or password")
        
    user = users[0]
    if not security.verify_password(form_data.password, user.get("hashed_password")):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.get("is_active"):
        raise HTTPException(status_code=400, detail="Inactive user")
    
    return {
        "access_token": security.create_access_token(user.get("id")),
        "token_type": "bearer",
    }

@router.post("/google", response_model=Token)
def google_auth(request_data: GoogleTokenRequest, db: Client = Depends(get_db)):
    """
    Verify Google OAuth token and issue our own custom JWT.
    """
    try:
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
        res = db.table("users").select("*").eq("email", email).execute()
        users = res.data
        
        if not users:
            # Create user if they don't exist
            new_user_data = {
                "email": email,
                "full_name": full_name,
                "auth_provider": "google"
            }
            insert_res = db.table("users").insert(new_user_data).execute()
            user = insert_res.data[0]
        else:
            user = users[0]
            if user.get("auth_provider") != "google":
                raise HTTPException(status_code=400, detail="User already registered with email/password")

        # Issue custom JWT
        return {
            "access_token": security.create_access_token(user.get("id")),
            "token_type": "bearer",
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Google token")
