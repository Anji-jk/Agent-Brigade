"""A prepared project plus a database and a fake agent runner, for the Builder tests."""

from datetime import datetime

from core.db import get_session, init_db, make_engine
from core.db.models import TrackerItem
from core.db.repositories import story_runs as runs
from core.db.repositories.projects import sync_env_project
from pipeline.runner.claude_runner import AgentError, AgentReply
from pipeline.stages.prepare import prepare_story
from tests.pipeline.stages.stage_setup import RUN, approved_project


class FakeRunner:
    """Stands in for the agent runner: remembers the request, can edit files like a Builder."""

    def __init__(self, write=None, text="**Changed:** x\n**Checked:** none run", error=None):
        self.write, self.text, self.error = write or {}, text, error
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        if self.error:
            raise AgentError(self.error)
        for name, content in self.write.items():
            (request.cwd / name).write_text(content, encoding="utf-8")
        return AgentReply(
            self.text,
            request.session_id,
            cost_usd=0.1234,
            turns=4,
            duration_ms=5200,
            input_tokens=100,
            output_tokens=50,
            cache_tokens=10,
            model_used="claude-sonnet",
        )


def build_project(
    tmp_path, *, setup=(), checks=(), approve=True, board=("SMT-62", "SMT-63"), prepared=True
):
    """(repo, settings, engine): an approved plan, a database with its run and board rows.

    `prepared`: the story branch and worktree exist, as after `prepare`.
    """
    repo, config, _ = approved_project(tmp_path, setup=setup, checks=checks)
    engine = init_db(make_engine(tmp_path / "brigade.db"))
    with get_session(engine) as session:
        project = sync_env_project(session, config)
        assert project is not None
        session.add(TrackerItem(key="SMT-61", project_id=project.id, type="story", summary="S"))
        session.flush()
        for key in board:
            session.add(
                TrackerItem(
                    key=key,
                    project_id=project.id,
                    type="sub-task",
                    summary=key,
                    parent_key="SMT-61",
                )
            )
        row = runs.start_run(session, project.id, "SMT-61", RUN, None, datetime(2026, 11, 13, 9, 0))
        row.status = runs.APPROVED if approve else runs.WAITING
    if prepared:
        prepare_story(config, RUN)
    return repo, config, engine
