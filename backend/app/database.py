"""
StockMind AI — Database Configuration
Async SQLAlchemy engine and session management.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# Async engine — conditionally apply pooling (SQLite doesn't support it)
_engine_kwargs = {
    "echo": settings.app_debug,
}
if "sqlite" not in settings.database_url:
    _engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    })

engine = create_async_engine(settings.database_url, **_engine_kwargs)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Create all tables (development only — see app/main.py's lifespan, which
    only calls this when APP_ENV=development; a Kubernetes deployment runs
    this once via k8s/db-init-job.yaml instead).

    SQLAlchemy's create_all() only creates tables for models that have been
    imported into the current process — it walks Base.metadata, which models
    only register themselves into by being imported, not by existing on disk.
    Importing every model module explicitly here means this is correct
    regardless of what the caller happens to have already imported (app.models
    .prompt.SystemPrompt used to go missing from fresh databases because
    prompt_service.py only imports it lazily, inside a function, to avoid a
    circular import — found by actually testing a from-scratch Postgres).
    """
    from app.models import (  # noqa: F401
        ai_commentary, broker_credential, market, portfolio, prediction,
        prompt, tracked_bracket, user, watchlist,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose database engine."""
    await engine.dispose()
