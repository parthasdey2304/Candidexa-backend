from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Candidexa Backend"
    
    # DB
    DATABASE_URL: str = "sqlite:///./candidexa.db"
    
    # JWT
    JWT_SECRET_KEY: str = "super-secret-key-please-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    
    # Google Auth
    GOOGLE_CLIENT_ID: str = ""
    
    # Mistral AI
    MISTRAL_API_KEY: str = ""
    
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra='ignore')

settings = Settings()
