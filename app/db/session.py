"""Database session management.

Supports both Supabase (PostgreSQL via REST API) and direct SQLAlchemy
async connections for application use.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from supabase import create_client, Client

from sqlalchemy.orm import declarative_base

# Base lives in app.db.base to avoid circular imports (session ↔ models ↔ ai_guard ↔ config)
from app.db.base import Base

from app.core.config import settings


# --- Supabase Client (for API-based access) ---

_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    """Get or create the Supabase client (singleton)."""
    global _supabase_client
    if _supabase_client is None:
        url: str = settings.SUPABASE_URL
        key: str = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
        if not url or not key:
            raise ValueError("Supabase credentials not found in environment variables.")
        _supabase_client = create_client(url, key)
    return _supabase_client


# --- SQLAlchemy Async Engine (for application use) ---

_async_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_async_engine() -> AsyncEngine:
    """Get or create the SQLAlchemy async engine (singleton)."""
    global _async_engine
    if _async_engine is None:
        if not settings.DATABASE_URL:
            raise ValueError("DATABASE_URL not configured for SQLAlchemy")
        # Normalize DATABASE_URL for psycopg3 async
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif db_url.startswith("postgresql+psycopg2://"):
            db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        _async_engine = create_async_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )
    return _async_engine


def get_async_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the SQLAlchemy async session factory."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting async DB session."""
    async_session_maker = get_async_session_maker()
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Close database connections."""
    global _async_engine, _async_session_maker, _supabase_client
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
    _async_session_maker = None
    _supabase_client = None