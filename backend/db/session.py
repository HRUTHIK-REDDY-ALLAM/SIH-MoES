"""
Varsha — Database session and engine configuration.

DATABASE_URL selects the backend:
  postgresql+asyncpg://user:pass@host:5432/varsha   production / docker (PostGIS)
  sqlite+aiosqlite:///./data/varsha.db               local dev, tests, offline demo (default)
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "varsha.db"

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Sync URL for scripts and the pipeline
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")

if IS_SQLITE:
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _engine_kwargs = {"connect_args": {"timeout": 30}}
else:
    _engine_kwargs = {"pool_size": 5, "pool_pre_ping": True}

# Async engine for FastAPI
engine = create_async_engine(DATABASE_URL, echo=False, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for the pipeline, scripts and static export
sync_engine = create_engine(SYNC_DATABASE_URL, echo=False, **_engine_kwargs)
SyncSession = sessionmaker(sync_engine, expire_on_commit=False)


if IS_SQLITE:
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    event.listen(sync_engine, "connect", _sqlite_pragmas)
    event.listen(engine.sync_engine, "connect", _sqlite_pragmas)


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
