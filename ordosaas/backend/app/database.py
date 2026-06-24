"""Async SQLAlchemy database setup."""
from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


# --- Async engine / session (application runtime) ---
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables that do not yet exist."""
    # Ensure all models are imported and registered on Base.metadata.
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- Sync engine / session (Alembic, scripts) ---
def _sync_url() -> str:
    return (
        settings.DATABASE_URL
        .replace("+asyncpg", "+psycopg2")
        .replace("+aiosqlite", "+pysqlite")
    )


sync_engine = create_engine(_sync_url(), echo=False, future=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


def get_db_sync():
    """Yield a synchronous session (used by Alembic / management commands)."""
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
