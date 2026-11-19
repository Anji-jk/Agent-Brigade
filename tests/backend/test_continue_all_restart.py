"""Continue all on a run that ended with a Failed task: a new loop retries it when it may."""

from fastapi.testclient import TestClient

from backend.main import create_app
from core.db import get_session
from core.db.models import StoryRun
from core.runs import run_directory
from pipeline.control import launch as lc
from pipeline.stages import story_loop
from tests.backend.test_task_continue_api import Launcher, Processes
from tests.pipeline.stages.stage_setup import FAIL, RUN
from tests.pipeline.stages.test_story_loop import StoryRunner, project


def world(tmp_path, retries_now, processes=None):
    """A run whose first task Failed for good (no retries when it ran), and the page's server
    started with `retries_now` retries allowed."""
    repo, config, engine = project(tmp_path, first_verify=(FAIL,), max_retries=0)
    config = config.model_copy(update={"data_dir": tmp_path})
    story_loop.run_story(config, RUN, StoryRunner(), engine=engine)
    launcher = Launcher()
    later = config.model_copy(update={"max_retries": retries_now})
    app = create_app(later, loop_launcher=launcher, command_line=processes or Processes())
    return repo, engine, app, launcher


def post(client):
    return client.post(f"/api/runs/{RUN}/continue")


def test_with_a_retry_left_a_new_loop_is_started_to_retry_it(tmp_path):
    repo, engine, app, launcher = world(tmp_path, retries_now=2)
    with TestClient(app) as client:
        reply = post(client)
    assert reply.status_code == 200
    body = reply.json()
    assert body["loop_started"] is True and body["continuing"] == ["SMT-62"]
    assert "retr" in body["detail"].lower() and "BRIGADE_MAX_RETRIES" not in body["detail"]
    assert launcher.calls == [RUN]


def test_with_no_retry_left_it_says_why_and_starts_nothing(tmp_path):
    repo, engine, app, launcher = world(tmp_path, retries_now=0)
    with TestClient(app) as client:
        reply = post(client)
    assert reply.status_code == 409
    assert "no task is stopped" in reply.json()["detail"].lower()
    assert "BRIGADE_MAX_RETRIES" in reply.json()["detail"]
    assert launcher.calls == []


def test_a_used_up_budget_refuses_the_restart(tmp_path):
    repo, engine, app, launcher = world(tmp_path, retries_now=2)
    with get_session(engine) as session:
        for row in session.query(StoryRun).filter(StoryRun.run_id == RUN):
            row.budget = 0.01
    with TestClient(app) as client:
        reply = post(client)
    assert reply.status_code == 409 and "budget" in reply.json()["detail"].lower()
    assert launcher.calls == []


def test_a_run_whose_loop_is_alive_is_not_restarted(tmp_path):
    processes = Processes()
    repo, engine, app, launcher = world(tmp_path, retries_now=2, processes=processes)
    folder = run_directory(repo, RUN)
    lc.write_launch(folder, lc.Launch(4242, ["py", "-m", "pipeline.stages", "loop", RUN], "t"))
    processes.running[4242] = f"python -m pipeline.stages loop {RUN}"
    with TestClient(app) as client:
        reply = post(client)
    assert reply.status_code == 409 and launcher.calls == []
