import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from core.db import init_db, make_engine
from core.db.upgrade import UpgradeError, add_missing_columns

OLD_STORY_RUNS = """
CREATE TABLE story_runs (
    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, story_key VARCHAR NOT NULL,
    status VARCHAR NOT NULL, branch VARCHAR, plan_file VARCHAR, budget NUMERIC(12, 4),
    cost NUMERIC(12, 4), started_at DATETIME, ended_at DATETIME
)
"""


def old_database(tmp_path):
    """A brigade.db made before story_runs had run_id and error, with one row in it."""
    engine = make_engine(tmp_path / "brigade.db")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text(OLD_STORY_RUNS))
        connection.execute(
            text("INSERT INTO story_runs (project_id, story_key, status) VALUES (1, 'SMT-1', 'x')")
        )
    return engine


def test_an_older_database_gets_the_new_columns_and_keeps_its_rows(tmp_path):
    engine = init_db(old_database(tmp_path))
    columns = {c["name"] for c in inspect(engine).get_columns("story_runs")}
    assert {"run_id", "error"} <= columns
    with engine.connect() as connection:
        assert connection.execute(text("SELECT story_key, run_id FROM story_runs")).all() == [
            ("SMT-1", None)
        ]
    engine.dispose()


def test_the_new_run_id_column_is_unique(tmp_path):
    engine = init_db(old_database(tmp_path))
    insert = text(
        "INSERT INTO story_runs (project_id, story_key, status, run_id) "
        "VALUES (1, 'SMT-1', 'x', 'SMT-1-20261112-a3f9')"
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(insert)
        connection.execute(insert)
    engine.dispose()


def test_a_current_database_needs_nothing_and_a_second_start_adds_nothing(tmp_path):
    engine = init_db(make_engine(tmp_path / "brigade.db"))
    assert add_missing_columns(engine) == []
    engine.dispose()


def test_a_column_that_may_not_be_empty_is_refused(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
    with pytest.raises(UpgradeError, match="projects.name cannot be added"):
        add_missing_columns(engine)
    engine.dispose()
