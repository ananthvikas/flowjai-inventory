"""
database.py — Engine creation, session dependency, table initialisation.

SQLite pragmas applied on each connection:
  - WAL mode: allows concurrent readers with one writer (important for dashboard + background alerts)
  - foreign_keys = ON: SQLite doesn't enforce FK by default
  - journal_mode WAL is safe to persist across restarts
"""

import os
from typing import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

# DATABASE_URL is set by the launcher as an absolute path before starting uvicorn.
# Fallback is relative to the working directory.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/flowjai.db")

# SQLite-specific connection args — ignored for PostgreSQL
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    echo=(os.getenv("SQL_ECHO") == "1"),
    connect_args=connect_args,
)


# Enforce FK constraints and WAL mode for every SQLite connection
@event.listens_for(Engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_db_and_tables(force: bool = False):
    """Create tables for a brand-new database.

    Skipped once the database is under migration control (has an
    alembic_version table): there, only migrations may change the schema.
    Creating tables behind the migrations' back is what broke upgrades before -
    a start-up while migrations were failing created the new tables, the
    recorded version stayed old, and every later upgrade then failed on
    "table already exists". `force` is for tests / fresh-install tooling.
    """
    if not force:
        from sqlalchemy import inspect
        if "alembic_version" in inspect(engine).get_table_names():
            return
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a session and closes it after the request."""
    with Session(engine) as session:
        yield session
