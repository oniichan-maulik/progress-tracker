"""Engine and session setup. Works with SQLite (local) and Postgres (hosted)."""

from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import database_url
from core.models import Base


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(url, pool_pre_ping=True)


# Columns added after the first release: {table: {column: DDL type}}.
# create_all() only creates missing tables, so existing databases get these via ALTER TABLE.
ADDED_COLUMNS = {
    "tasks": {"deletion_requested_at": "TIMESTAMP", "deletion_reason": "TEXT DEFAULT ''"},
}


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in ADDED_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


@lru_cache(maxsize=1)
def _default_sessionmaker() -> sessionmaker[Session]:
    engine = make_engine(database_url())
    init_db(engine)
    return sessionmaker(engine, expire_on_commit=False)


def get_session() -> Session:
    return _default_sessionmaker()()
