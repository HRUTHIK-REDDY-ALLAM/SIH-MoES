"""
Varsha — Database session and engine configuration.
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://varsha:changeme_in_production@localhost:5432/varsha"
)

# Sync URL for Alembic migrations and scripts
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

# Async engine for FastAPI
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for migrations and data loading scripts
sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
