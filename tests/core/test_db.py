import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from core.db import get_session, init_db, make_engine
from core.db.models import (
    AgentRun,
    Attempt,
    BudgetReservation,
    ChatSession,
    Check,
    Merge,
    Project,
    PublishRecord,
    StoryRun,
    SubTask,
    TrackerItem,
)

TABLES = {
    "projects",
    "tracker_items",
    "chat_sessions",
    "publish_records",
    "story_runs",
    "sub_tasks",
    "attempts",
    "agent_runs",
    "checks",
    "merges",
    "budget_reservations",
}


@pytest.fixture
def engine(tmp_path):
    engine = init_db(make_engine(tmp_path / "data" / "brigade.db"))
    yield engine
    engine.dispose()


def add_project(session) -> Project:
    project = Project(name="Skill Matrix", local_path="C:/sm", base_branch="main")
    session.add(project)
    session.flush()
    return project


def test_all_11_tables_exist(engine, tmp_path):
    assert (tmp_path / "data" / "brigade.db").is_file()
    assert set(inspect(engine).get_table_names()) == TABLES


def test_init_db_twice_is_safe(engine):
    init_db(engine)
    assert len(inspect(engine).get_table_names()) == 11


def test_wal_foreign_keys_and_busy_timeout_are_on(engine):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_deleting_a_project_in_use_is_refused(engine):
    with get_session(engine) as s:
        project = add_project(s)
        s.add(TrackerItem(key="SM-1", project_id=project.id, type="epic", summary="Login"))
    with pytest.raises(IntegrityError):
        with get_session(engine) as s:
            s.execute(text("DELETE FROM projects"))


def test_unknown_parent_is_refused(engine):
    with pytest.raises(IntegrityError):
        with get_session(engine) as s:
            project = add_project(s)
            s.add(
                TrackerItem(
                    key="SM-2", project_id=project.id, type="story", summary="x", parent_key="NO-1"
                )
            )


def test_a_full_chain_round_trips(engine):
    with get_session(engine) as s:
        p = add_project(s)
        s.add_all(
            [
                TrackerItem(key="SM-1", project_id=p.id, type="epic", summary="Epic"),
                TrackerItem(
                    key="SM-2", project_id=p.id, type="story", summary="Story", parent_key="SM-1"
                ),
                TrackerItem(
                    key="SM-3", project_id=p.id, type="sub-task", summary="Sub", parent_key="SM-2"
                ),
            ]
        )
        s.flush()
        chat = ChatSession(project_id=p.id, claude_session_id="abc")
        s.add(chat)
        s.flush()
        s.add(PublishRecord(chat_session_id=chat.id, proposed_items=[{"summary": "Story"}]))
        run = StoryRun(project_id=p.id, story_key="SM-2", status="planned", budget=5.0)
        s.add(run)
        s.flush()
        sub = SubTask(story_run_id=run.id, key="SM-3", status="queued", depends_on="SM-4,SM-5")
        s.add(sub)
        s.flush()
        attempt = Attempt(sub_task_id=sub.id, number=1)
        s.add(attempt)
        s.flush()
        agent = AgentRun(attempt_id=attempt.id, role="builder", cost=0.42)
        s.add(agent)
        s.flush()
        s.add_all(
            [
                Check(attempt_id=attempt.id, kind="tests", passed=True),
                Merge(attempt_id=attempt.id, kind="fast-forward", commit="9489c45"),
                BudgetReservation(story_run_id=run.id, agent_run_id=agent.id, amount=1.5),
            ]
        )

    with get_session(engine) as s:
        tracker_item = s.get(TrackerItem, "SM-2")
        assert tracker_item is not None
        assert tracker_item.parent_key == "SM-1"
        assert s.scalars(select(PublishRecord)).one().proposed_items == [{"summary": "Story"}]
        assert s.scalars(select(SubTask)).one().depends_on == "SM-4,SM-5"
        assert s.scalars(select(AgentRun)).one().cost == pytest.approx(0.42)
        assert s.scalars(select(StoryRun)).one().budget == pytest.approx(5.0)
        assert s.scalars(select(Merge)).one().commit == "9489c45"
        assert s.scalars(select(BudgetReservation)).one().released is False
