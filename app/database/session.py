import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

# --- Engine ---
# echo=True only in debug/dev so SQL statements aren't dumped in production logs.
engine: AsyncEngine = create_async_engine(
    settings.DB_CONNECTION,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # detects stale connections before using them
    pool_recycle=1800,   # recycle connections every 30 min (avoids server-side timeouts)
)

# --- Session factory ---
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session per request.

    Commits on clean exit, rolls back on any exception, and always
    closes the session to release the connection back to the pool.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """
    Lightweight connectivity check, used at startup and in health checks.
    """
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connection check failed: %s", exc)
        return False


async def dispose_engine() -> None:
    """
    Cleanly dispose of the engine's connection pool on application shutdown.
    """
    await engine.dispose()