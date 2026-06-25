"""Async SQLAlchemy 2.0 engine, session factory, and init.

Runs on SQLite (default, zero-config) and Postgres. On Postgres it uses pgvector
when available and transparently falls back to JSON-encoded embeddings when not,
so it deploys to any managed Postgres (Render, Neon, Supabase, ...).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = logging.getLogger("app.db")

# Set during init_db(): True when the pgvector extension is usable.
PGVECTOR_OK = False

if settings.db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif settings.pg_ssl_enabled:
    connect_args = {"ssl": True}
else:
    connect_args = {}

engine = create_async_engine(
    settings.db_url, echo=False, pool_pre_ping=True, connect_args=connect_args
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Enable pgvector if possible, then create all tables. Idempotent."""
    global PGVECTOR_OK
    from . import models  # noqa: F401  (register models on Base.metadata)

    if settings.is_postgres:
        from sqlalchemy import text

        try:
            # separate transaction: a failed CREATE EXTENSION must not abort create_all
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            PGVECTOR_OK = True
        except Exception as exc:  # pragma: no cover - depends on grants/host
            PGVECTOR_OK = False
            log.warning("pgvector unavailable (%s); embeddings will use JSON columns", exc)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    log.info(
        "database initialized (%s, pgvector=%s)",
        "postgres" if settings.is_postgres else "sqlite",
        PGVECTOR_OK,
    )
