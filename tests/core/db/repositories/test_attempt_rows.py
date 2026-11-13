from datetime import datetime

import pytest

from core.db import get_session, init_db, make_engine
from core.db.models import Project, TrackerItem
from core.db.repositories import attempt_rows as b
from core.db.repositories import story_runs as runs
from pipeline.runner.claude_runner import AgentReply

NOON = datetime(2026, 11, 13, 12, 0)


@pytest.fixture
def engine(tmp_path):
    engine = init_db(make_engine(tmp_path / "brigade.db"))
    with get_session(engine) as s:
        s.add(Project(id=1, name="SM", local_path="C:/sm", base_branch="main"))
        s.flush()
        for key, kind in (("SMT-61", "story"), ("SMT-62", "sub-task")):
            s.add(TrackerItem(key=key, project_id=1, type=kind, summary=key))
        s.flush()
        runs.start_run(s, 1, "SMT-61", "SMT-61-20261113-aaaa", None, NOON)
    yield engine
    engine.dispose()


def a_story(s):
    story = runs.get_run(s, 1, "SMT-61-20261113-aaaa")
    assert story is not None
    return story


def test_the_rows_follow_one_attempt_from_start_to_finish(engine):
    with get_session(engine) as s:
        story = a_story(s)
        sub = b.sub_task_row(s, story.id, "SMT-62", "small", ["SMT-60"])
        assert b.sub_task_row(s, story.id, "SMT-62", "small", []).id == sub.id  # one row per key
        attempt = b.start_attempt(s, sub, 1, "agent-attempt/x/SMT-62-1", "C:/bw/x", NOON)
        row = b.start_agent_run(s, attempt, "builder", "sonnet", "low", "sid", NOON)
        assert (sub.status, sub.current_stage, row.status) == ("running", "builder", "running")
        reply = AgentReply("ok", "sid2", 0.25, 5, 2500, 11, 22, 33, "claude-x")
        b.finish_agent_run(s, row, reply, error=None, now=NOON)
        b.finish_attempt(
            s,
            attempt,
            sub,
            outcome="built",
            reason=None,
            stage="builder",
            status=b.RUNNING,
            now=NOON,
        )
        assert (row.status, row.cost, row.turns, row.duration_s) == ("done", 0.25, 5, 2)
        assert (row.session_id, row.model_used, row.cache_tokens) == ("sid2", "claude-x", 33)
        assert (attempt.outcome, attempt.ended_at) == ("built", NOON)
        assert sub.depends_on == "SMT-60" and sub.size == "small"
        assert [r.id for r in b.agent_runs_of(s, attempt.id)] == [row.id]


def test_an_agent_that_did_not_answer_is_an_error_row(engine):
    with get_session(engine) as s:
        story = a_story(s)
        sub = b.sub_task_row(s, story.id, "SMT-62", None, [])
        attempt = b.start_attempt(s, sub, 1, "br", "wt", NOON)
        row = b.start_agent_run(s, attempt, "builder", "sonnet", "low", "sid", NOON)
        b.finish_agent_run(s, row, None, error="timed out", now=NOON)
        assert (row.status, row.exit_reason, row.session_id, row.cost) == (
            "error",
            "timed out",
            "sid",
            None,
        )


def test_a_key_that_is_not_on_the_board_is_refused(engine):
    with get_session(engine) as s:
        story = a_story(s)
        with pytest.raises(b.BuildRecordError, match="press Sync"):
            b.sub_task_row(s, story.id, "SMT-99", None, [])
