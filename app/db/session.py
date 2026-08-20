"""Database session management.

Supports both Supabase (PostgreSQL via REST API) and direct SQLAlchemy
connections for migrations and complex queries.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from supabase import create_client, Client

from app.core.config import settings
from app.db.models import Base


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


# --- SQLAlchemy Engine (for migrations and direct DB access) ---

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the SQLAlchemy engine (singleton)."""
    global _engine
    if _engine is None:
        if not settings.DATABASE_URL:
            raise ValueError("DATABASE_URL not configured for SQLAlchemy")
        # Normalize DATABASE_URL for psycopg3
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif db_url.startswith("postgresql+psycopg2://"):
            db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )
    return _engine


def get_session_factory():
    """Get or create the SQLAlchemy session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Get a SQLAlchemy database session (context manager)."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Initialize database tables (use with caution in production)."""
    Base.metadata.create_all(bind=get_engine())


def close_db() -> None:
    """Close database connections."""
    global _engine, _SessionLocal, _supabase_client
    if _engine:
        _engine.dispose()
        _engine = None
    _SessionLocal = None
    _supabase_client = None
