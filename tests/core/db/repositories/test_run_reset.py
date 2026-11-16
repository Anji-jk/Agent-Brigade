from datetime import datetime

import pytest
from sqlalchemy import func, select

from core.db import get_session, init_db, make_engine
from core.db.models import (
    AgentRun,
    Attempt,
    BudgetReservation,
    Check,
    Merge,
    Project,
    StoryRun,
    SubTask,
    TrackerItem,
)
from core.db.repositories import attempt_rows as b
from core.db.repositories import run_reset as r
from core.db.repositories import story_runs as runs

NOON = datetime(2026, 11, 13, 12, 0)
MINE, OTHER = "SMT-61-20261113-aaaa", "SMT-70-20261113-bbbb"


def a_built_task(s, run_id, key):
    """One sub-task with an attempt that was Done and merged, with every row that goes with it."""
    story = runs.get_run(s, 1, run_id)
    assert story is not None
    sub = b.sub_task_row(s, story.id, key, "small", [])
    attempt = b.start_attempt(s, sub, 1, f"agent-attempt/{run_id}/{key}-1", "C:/bw/x", NOON)
    row = b.start_agent_run(s, attempt, "builder", "sonnet", "low", "sid", NOON)
    s.add_all([Check(attempt_id=attempt.id, kind="verify", passed=True)])
    s.add(Merge(attempt_id=attempt.id, kind="fast-forward", commit="abc"))
    s.add(BudgetReservation(story_run_id=story.id, agent_run_id=row.id, amount=1))
    s.flush()


@pytest.fixture
def engine(tmp_path):
    engine = init_db(make_engine(tmp_path / "brigade.db"))
    with get_session(engine) as s:
        s.add(Project(id=1, name="SM", local_path="C:/sm", base_branch="main"))
        s.flush()
        for key, kind in (
            ("SMT-61", "story"), ("SMT-62", "sub-task"),
            ("SMT-70", "story"), ("SMT-71", "sub-task"),
        ):  # fmt: skip
            s.add(TrackerItem(key=key, project_id=1, type=kind, summary=key))
        s.flush()
        runs.start_run(s, 1, "SMT-61", MINE, None, NOON)
        runs.start_run(s, 1, "SMT-70", OTHER, None, NOON)
        a_built_task(s, MINE, "SMT-62")
        a_built_task(s, OTHER, "SMT-71")
    yield engine
    engine.dispose()


def count(s, model):
    return s.scalar(select(func.count()).select_from(model))


def test_every_row_the_builds_of_the_run_wrote_is_removed(engine):
    with get_session(engine) as s:
        removed = r.reset_run(s, MINE)
    assert removed == {
        "sub_tasks": 1, "attempts": 1, "agent_runs": 1, "checks": 1, "merges": 1,
        "budget_reservations": 1,
    }  # fmt: skip
    with get_session(engine) as s:  # only the other run's rows are left
        for model in (SubTask, Attempt, AgentRun, Check, Merge, BudgetReservation):
            assert count(s, model) == 1


def test_the_run_itself_keeps_its_status_for_the_next_build(engine):
    with get_session(engine) as s:
        row = runs.get_run(s, 1, MINE)
        assert row is not None
        row.status = runs.APPROVED
    with get_session(engine) as s:
        r.reset_run(s, MINE)
    with get_session(engine) as s:
        story = runs.get_run(s, 1, MINE)
        assert story is not None and story.status == runs.APPROVED
        assert s.scalar(select(StoryRun.id).where(StoryRun.run_id == OTHER)) is not None


def test_a_run_without_rows_or_unknown_to_the_database_is_a_quiet_nothing(engine):
    with get_session(engine) as s:
        r.reset_run(s, MINE)
        assert set(r.reset_run(s, MINE).values()) == {0}
        assert r.reset_run(s, "SMT-99-20261113-cccc") == {}
