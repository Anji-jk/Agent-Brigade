from datetime import datetime, timedelta

import pytest

from core.db import get_session, init_db, make_engine
from core.db.models import Project, TrackerItem
from core.db.repositories import story_runs as r

NOON = datetime(2026, 11, 12, 12, 0)


@pytest.fixture
def engine(tmp_path):
    engine = init_db(make_engine(tmp_path / "brigade.db"))
    with get_session(engine) as s:
        s.add(Project(id=1, name="Skill Matrix", local_path="C:/sm", base_branch="main"))
        s.flush()
        for key in ("SMT-56", "SMT-70"):
            s.add(TrackerItem(key=key, project_id=1, type="story", summary=key))
    yield engine
    engine.dispose()


def start(s, run_id, key="SMT-56", minutes=0, budget=None):
    return r.start_run(s, 1, key, run_id, budget, NOON + timedelta(minutes=minutes))


def test_a_run_starts_planning_with_its_id_and_budget(engine):
    with get_session(engine) as s:
        start(s, "SMT-56-20261112-aaaa", budget=12)
    with get_session(engine) as s:
        row = r.get_run(s, 1, "SMT-56-20261112-aaaa")
        assert row.status == r.PLANNING and row.budget == 12.0 and row.started_at == NOON
        assert r.run_id_taken(s, "SMT-56-20261112-aaaa")
        assert not r.run_id_taken(s, "SMT-56-20261112-bbbb")
        assert r.get_run(s, 2, "SMT-56-20261112-aaaa") is None  # another project's view


def test_runs_of_a_story_are_newest_first_and_the_latest_is_per_story(engine):
    with get_session(engine) as s:
        start(s, "a", minutes=0)
        start(s, "b", minutes=5)
        start(s, "c", key="SMT-70", minutes=1)
    with get_session(engine) as s:
        assert [row.run_id for row in r.runs_of_story(s, 1, "SMT-56")] == ["b", "a"]
        latest = r.latest_runs(s, 1)
        assert latest["SMT-56"].run_id == "b" and latest["SMT-70"].run_id == "c"


def test_runs_with_a_status(engine):
    with get_session(engine) as s:
        start(s, "a").status = r.APPROVED
        start(s, "b")
    with get_session(engine) as s:
        assert [row.run_id for row in r.runs_with_status(s, 1, "SMT-56", r.APPROVED)] == ["a"]


def test_runs_left_planning_by_a_stop_are_marked_failed(engine):
    with get_session(engine) as s:
        start(s, "a")
        start(s, "b").status = r.WAITING
    later = NOON + timedelta(hours=1)
    with get_session(engine) as s:
        assert r.fail_unfinished(s, "Brigade stopped while planning", later) == 1
    with get_session(engine) as s:
        row = r.get_run(s, 1, "a")
        assert (row.status, row.error, row.ended_at) == (
            r.FAILED,
            "Brigade stopped while planning",
            later,
        )
        assert r.get_run(s, 1, "b").status == r.WAITING
