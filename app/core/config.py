from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRETS = {
    "super-secret-key-please-change-in-prod",
    "replace_me",
    "replace_with_a_long_random_development_secret",
    "your-super-secret-key",
    "secret",
}


class Settings(BaseSettings):
    PROJECT_NAME: str = "Candidexa Backend"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"  # development | test | production
    LOG_LEVEL: str = "INFO"

    # --- Frontend origins (CORS) ---
    FRONTEND_ORIGINS: str = "http://localhost:3000"

    # --- Supabase (the persistence layer for this service) ---
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # --- Database (PostgreSQL via Supabase or managed) ---
    DATABASE_URL: str = ""

    # --- JWT ---
    JWT_SECRET: str = "super-secret-key-please-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = ""

    # --- AI providers (server-side only; never exposed to the frontend) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small"

    # --- Redis (for rate limiting) ---
    REDIS_URL: str = ""

    # --- AI guard rails ---
    AI_REQUESTS_PER_MINUTE: int = 10
    AI_REQUESTS_PER_DAY: int = 50
    AI_TIMEOUT_SECONDS: int = 30
    AI_MAX_INPUT_CHARS: int = 20000
    AI_DAILY_TOKEN_LIMIT: int = 10000
    AI_MONTHLY_TOKEN_LIMIT: int = 100000

    # --- File upload limits ---
    MAX_RESUME_SIZE_MB: int = 10
    MAX_JSON_BODY_MB: int = 1

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @field_validator("ENVIRONMENT")
    @classmethod
    def _normalise_environment(cls, v: str) -> str:
        v = v.strip().lower()
        allowed = {"development", "test", "production"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("FRONTEND_ORIGINS")
    @classmethod
    def _origins_not_wildcard(cls, v: str) -> str:
        if "*" in v:
            raise ValueError("FRONTEND_ORIGINS must not contain '*' (credentials are enabled)")
        return v

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def _validate_jwt_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "RS256"}
        if v not in allowed:
            raise ValueError(f"JWT_ALGORITHM must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v:
            return v
        allowed_prefixes = (
            "postgresql://",
            "postgresql+psycopg://",
            "postgresql+asyncpg://",
            "sqlite://",
        )
        if not v.startswith(allowed_prefixes):
            raise ValueError(f"DATABASE_URL must start with one of {allowed_prefixes}")
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.FRONTEND_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _validate_production_security(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self

        problems = []
        if self.JWT_SECRET in _INSECURE_SECRETS or len(self.JWT_SECRET) < 32:
            problems.append("JWT_SECRET must be a random value of at least 32 characters")
        if not self.SUPABASE_URL:
            problems.append("SUPABASE_URL is required")
        if not (self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_ANON_KEY):
            problems.append("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY is required")
        if not self.DATABASE_URL:
            problems.append("DATABASE_URL is required")
        if self.DATABASE_URL.startswith("sqlite://"):
            problems.append("SQLite is not allowed in production")
        if "*" in self.FRONTEND_ORIGINS:
            problems.append("FRONTEND_ORIGINS must not contain '*' in production")
        if self.AI_REQUESTS_PER_MINUTE <= 0:
            problems.append("AI_REQUESTS_PER_MINUTE must be positive")
        if self.AI_REQUESTS_PER_DAY <= 0:
            problems.append("AI_REQUESTS_PER_DAY must be positive")
        if self.MAX_RESUME_SIZE_MB <= 0:
            problems.append("MAX_RESUME_SIZE_MB must be positive")
        if self.MAX_JSON_BODY_MB <= 0:
            problems.append("MAX_JSON_BODY_MB must be positive")
        if problems:
            raise ValueError(
                "Refusing to start in production with insecure configuration: "
                + "; ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
