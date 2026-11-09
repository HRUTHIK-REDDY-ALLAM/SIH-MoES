"""
Varsha — Create database tables.

    python scripts/create_tables.py

Works for SQLite (default, data/varsha.db) and PostgreSQL + PostGIS
(set DATABASE_URL). scripts/bootstrap_demo.py calls this for you.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from backend.db.models import Base  # noqa: E402
from backend.db.session import SYNC_DATABASE_URL, sync_engine  # noqa: E402


def main():
    print(f"Connecting to: {SYNC_DATABASE_URL.split('@')[-1]}")
    if sync_engine.dialect.name == "postgresql":
        with sync_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()
            print(f"PostGIS version: {conn.execute(text('SELECT PostGIS_Version()')).scalar()}")
    Base.metadata.create_all(sync_engine)
    print("Tables:", ", ".join(sorted(inspect(sync_engine).get_table_names())))


if __name__ == "__main__":
    main()
