"""The central database. Import models from core.db.models, sessions from here."""

from sqlalchemy import Engine

from core.db.engine import get_engine, get_session, make_engine, session_factory
from core.db.models import Base


def init_db(engine: Engine | None = None) -> Engine:
    """Create any missing tables. Safe to call on every start; never drops or alters.

    No migrations yet: the schema still changes in Phase 2. Alembic comes once it settles.
    """
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    return engine


__all__ = [
    "Base",
    "get_engine",
    "get_session",
    "init_db",
    "make_engine",
    "session_factory",
]
