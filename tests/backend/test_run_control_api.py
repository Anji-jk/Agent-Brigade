import json

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from core.db import get_session
from core.db.models import StoryRun, TrackerItem
from core.db.repositories import story_runs as runs
from core.runs import run_directory
from pipeline.control import launch as lc
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.test_story_loop import project

PID = 4242
OURS = f"python -m pipeline.stages loop {RUN}"


class Launcher:
    """Stands in for the real launch: records the call and writes the record a loop would."""

    def __init__(self):
        self.calls = []

    def __call__(self, run_dir, run_id, repository):
        self.calls.append((run_dir, run_id, repository))
        launch = lc.Launch(PID, ["py", "-m", "pipeline.stages", "loop", run_id], "t")
        lc.write_launch(run_dir, launch)
        return launch


class Processes:
    """Which process ids are running: the loop's, until a test ends it."""

    def __init__(self):
        self.running = {PID: OURS}

    def __call__(self, pid):
        return self.running.get(pid)


@pytest.fixture
def world(tmp_path):
    repo, config, _ = project(tmp_path)
    launcher, processes = Launcher(), Processes()
    app = create_app(
        config.model_copy(update={"data_dir": tmp_path}),
        loop_launcher=launcher,
        command_line=processes,
    )
    with TestClient(app) as client:
        yield repo, client, launcher, processes, app


def start(client, run_id=RUN):
    return client.post(f"/api/runs/{run_id}/start")


def test_start_launches_the_loop_once_and_says_it_is_running(world):
    repo, client, launcher, _, _ = world
    reply = start(client)
    assert reply.status_code == 200
    body = reply.json()
    assert (body["run_id"], body["state"], body["pid"]) == (RUN, "running", PID)
    ((run_dir, run_id, repository),) = launcher.calls
    assert (run_dir, run_id) == (run_directory(repo, RUN), RUN)
    assert (repository / "pipeline" / "stages" / "__main__.py").exists()  # the Brigade folder


def test_a_second_start_while_it_runs_is_refused(world):
    _, client, launcher, _, _ = world
    start(client)
    again = start(client)
    assert again.status_code == 409 and "already running" in again.json()["detail"]
    assert len(launcher.calls) == 1


def test_a_finished_run_is_not_started_again(world):
    repo, client, launcher, processes, _ = world
    start(client)
    processes.running.clear()
    (run_directory(repo, RUN) / "story-report.json").write_text(json.dumps({"ok": True}), "utf-8")
    again = start(client)
    assert again.status_code == 409 and "already finished" in again.json()["detail"]


@pytest.mark.parametrize("report", [None, False])
def test_a_run_that_stopped_or_was_interrupted_is_continued_not_started(world, report):
    repo, client, _, processes, _ = world
    start(client)
    processes.running.clear()
    if report is not None:
        (run_directory(repo, RUN) / "story-report.json").write_text(
            json.dumps({"ok": report}), "utf-8"
        )
    again = start(client)
    assert again.status_code == 409 and "Continue" in again.json()["detail"]


def test_only_an_approved_plan_can_be_started(world):
    _, client, launcher, _, app = world
    with get_session(app.state.engine) as session:
        session.query(StoryRun).filter_by(run_id=RUN).update({"status": runs.WAITING})
    reply = start(client)
    assert reply.status_code == 409 and "approved" in reply.json()["detail"]
    assert launcher.calls == []


@pytest.mark.parametrize("run_id", ["SMT-61-20990101-ffff", "bad.id", "a b"])
def test_a_run_that_is_not_in_the_project_is_not_found(world, run_id):
    _, client, launcher, _, _ = world
    assert start(client, run_id).status_code == 404
    assert launcher.calls == []


def story_lines(client):
    return {line["key"]: line for line in client.get("/api/orchestrator/stories").json()}


def test_the_list_has_only_stories_with_an_approved_plan_and_their_runs(world):
    _, client, _, _, app = world
    with get_session(app.state.engine) as session:
        first = session.query(StoryRun).first()
        item = TrackerItem(key="SMT-90", project_id=first.project_id, type="story", summary="x")
        session.add(item)
        session.flush()
        runs.start_run(session, first.project_id, "SMT-90", "SMT-90-x1", None, first.started_at)
    lines = story_lines(client)
    assert list(lines) == ["SMT-61"]
    (line,) = lines["SMT-61"]["runs"]
    assert (line["run_id"], line["plan_status"], line["build_state"]) == (
        RUN,
        "approved",
        "not_started",
    )
    assert lines["SMT-61"]["action"] == "start"


def test_the_list_follows_a_run_from_start_to_finished(world):
    repo, client, _, processes, _ = world
    start(client)
    assert story_lines(client)["SMT-61"]["action"] == "running"
    processes.running.clear()
    (run_directory(repo, RUN) / "story-report.json").write_text(json.dumps({"ok": False}), "utf-8")
    assert story_lines(client)["SMT-61"]["action"] == "continue"
    (run_directory(repo, RUN) / "story-report.json").write_text(json.dumps({"ok": True}), "utf-8")
    assert story_lines(client)["SMT-61"]["action"] == "done"


def test_progress_tells_the_build_state(world):
    _, client, _, _, _ = world
    assert client.get(f"/api/runs/{RUN}/progress").json()["build_state"] == "not_started"
    start(client)
    assert client.get(f"/api/runs/{RUN}/progress").json()["build_state"] == "running"


def test_a_paused_run_is_continued_not_started(world):
    repo, client, _, processes, _ = world
    start(client)
    processes.running.clear()
    tasks = {"SMT-62": {"status": "stopped"}}
    (run_directory(repo, RUN) / "story-report.json").write_text(
        json.dumps({"ok": False, "tasks": tasks}), "utf-8"
    )
    again = start(client)
    assert again.status_code == 409 and "paused" in again.json()["detail"]
    assert story_lines(client)["SMT-61"]["action"] == "continue"
