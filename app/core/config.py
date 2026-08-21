from __future__ import annotations
import os
import secrets
from functools import lru_cache
from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    ENVIRONMENT: str = "development"
    APP_NAME: str = "Candidexa Backend"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    # --- Database ---
    DATABASE_URL: str

    # --- JWT ---
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_PRIVATE_KEY: str | None = None
    JWT_PUBLIC_KEY: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Field-level encryption (AES-256-GCM) ---
    # 32 bytes base64. Generate: python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
    FIELD_ENCRYPTION_KEY: str
    # 32 bytes base64 for HMAC blind index. MUST differ from FIELD_ENCRYPTION_KEY.
    FIELD_BLIND_INDEX_KEY: str

    # --- CORS ---
    FRONTEND_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://127.0.0.1:3000,http://127.0.0.1:3001,https://candidexa.vercel.app,https://candidexa.app,https://www.candidexa.app"

    # --- Rate limits ---
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_AUTH_PER_MIN: int = 5
    RATE_LIMIT_API_PER_MIN: int = 60
    RATE_LIMIT_AI_PER_MIN: int = 10

    # --- AI gateway ---
    AI_REQUESTS_PER_MINUTE: int = 10
    AI_DAILY_TOKEN_LIMIT: int = 10000
    AI_MONTHLY_TOKEN_LIMIT: int = 100000
    AI_MONTHLY_SPEND_USD_LIMIT: float = 25.0
    AI_MAX_INPUT_TOKENS: int = 8000
    AI_MAX_OUTPUT_TOKENS: int = 2000
    AI_TIMEOUT_SECONDS: int = 45
    AI_CIRCUIT_BREAKER_THRESHOLD: int = 5
    AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 60

    GEMINI_API_KEY: str | None = None
    MISTRAL_API_KEY: str | None = None

    # --- Upload ---
    MAX_RESUME_SIZE_MB: int = 10
    MAX_JSON_BODY_MB: int = 1

    @property
    def frontend_origins_list(self) -> list[str]:
        return [o.strip() for o in self.FRONTEND_ORIGINS.split(",") if o.strip()]

    @field_validator("JWT_SECRET")
    @classmethod
    def _strong_jwt_secret(cls, v: str) -> str:
        if v in {"replace_me", "", "changeme"}:
            raise ValueError("JWT_SECRET must be set to a strong secret")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be >= 32 characters")
        return v

    @field_validator("FIELD_ENCRYPTION_KEY", "FIELD_BLIND_INDEX_KEY")
    @classmethod
    def _strong_field_key(cls, v: str) -> str:
        if v in {"replace_me", ""}:
            raise ValueError("Field encryption key must be set")
        import base64
        try:
            raw = base64.b64decode(v)
            if len(raw) != 32:
                raise ValueError("Field key must decode to 32 bytes")
        except Exception as e:
            raise ValueError(f"Field key not valid base64-32: {e}")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def _validate_prod(cls, v: str) -> str:
        if v.lower() == "production":
            if "localhost" in os.getenv("FRONTEND_ORIGINS", ""):
                raise ValueError("Production cannot have localhost in FRONTEND_ORIGINS")
            if "*" in os.getenv("FRONTEND_ORIGINS", ""):
                raise ValueError("Wildcard CORS forbidden in production")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()