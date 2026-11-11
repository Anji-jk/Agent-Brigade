"""SQLite engine and sessions for the one central database (brigade.db)."""

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from core.settings import get_settings

BUSY_TIMEOUT_MS = 5000  # a writer waits this long for another writer instead of failing


def make_engine(db_path: Path) -> Engine:
    """Engine for one SQLite file, with WAL and foreign keys on for every connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},  # FastAPI uses several threads
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")  # API, runner and agents write at once
        cursor.execute("PRAGMA foreign_keys=ON")  # SQLite leaves them off by default
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, much faster
        cursor.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    """The engine for the configured database: <BRIGADE_DATA_DIR>/brigade.db."""
    return make_engine(get_settings().db_path)


def session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    """One unit of work: commits on success, rolls back on error, always closes."""
    session = session_factory(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
