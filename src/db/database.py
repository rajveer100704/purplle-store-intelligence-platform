"""
db/database.py – SQLAlchemy async engine and session factory.

Uses aiosqlite for async I/O compatible with FastAPI's async handlers.
Also provides a synchronous session for use in synchronous scripts
(pipeline.py, replay.py).
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ──────────────────────────────────────────────────────────────────────────────
# Base ORM class
# ──────────────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Engine configuration
# ──────────────────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///./store_intelligence.db"
)

# Async engine (for FastAPI)
async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine (for scripts)
SYNC_DATABASE_URL = DATABASE_URL.replace(
    "sqlite+aiosqlite://", "sqlite://"
).replace("+aiosqlite", "")

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ──────────────────────────────────────────────────────────────────────────────

async def create_tables() -> None:
    """Create all ORM tables if they don't exist."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def create_tables_sync() -> None:
    """Synchronous table creation (for CLI scripts)."""
    Base.metadata.create_all(bind=sync_engine)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
