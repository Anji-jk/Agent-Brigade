"""The central database. Import models from core.db.models, sessions from here."""

from sqlalchemy import Engine

from core.db.engine import get_engine, get_session, make_engine, session_factory
from core.db.models import Base
from core.db.upgrade import add_missing_columns


def init_db(engine: Engine | None = None) -> Engine:
    """Create missing tables, then add columns an older brigade.db lacks. Safe on every start.

    Never drops or changes what is there. No migrations yet: Alembic comes once the schema
    settles; until then a new column must allow empty values (see upgrade.py).
    """
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    return engine


__all__ = [
    "Base",
    "get_engine",
    "get_session",
    "init_db",
    "make_engine",
    "session_factory",
]
