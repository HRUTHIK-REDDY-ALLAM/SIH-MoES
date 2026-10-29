"""
Varsha — Create Database Tables

Standalone script to create all tables in the database.
Run after docker compose up to initialize the schema.

Usage:
    python scripts/create_tables.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from backend.db.models import Base
from backend.db.session import SYNC_DATABASE_URL


def main():
    print(f"Connecting to: {SYNC_DATABASE_URL}")
    engine = create_engine(SYNC_DATABASE_URL)

    # Verify PostGIS
    with engine.connect() as conn:
        result = conn.execute(text("SELECT PostGIS_Version();"))
        version = result.scalar()
        print(f"PostGIS version: {version}")

    # Create all tables
    Base.metadata.create_all(engine)
    print("✅ All tables created successfully")

    # List tables
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [row[0] for row in result]
        print(f"Tables: {', '.join(tables)}")


if __name__ == "__main__":
    main()
