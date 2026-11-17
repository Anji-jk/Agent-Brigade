"""Continue over HTTP: which tasks may go on, what is refused, and finding an interrupted one."""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from core.db import get_session
from core.db.models import StoryRun
from core.runs import run_directory
from pipeline.control import continue_request as cont
from pipeline.control import launch as lc
from pipeline.control import task_control as tc
from pipeline.stages import checkpoint, story_loop
from pipeline.stages.builder_run import build_attempt
from pipeline.workspace import layout
from pipeline.workspace.worktrees import remove_worktree
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import TeamRunner
from tests.pipeline.stages.test_story_loop import StoryRunner, project
from tests.pipeline.stages.test_story_loop_stop import AskingStory

PID = 4242
OURS = f"python -m pipeline.stages loop {RUN}"


class Launcher:
    def __init__(self):
        self.calls, self.lock_seen = [], []

    def __call__(self, run_dir, run_id, repository):
        self.calls.append(run_id)
        self.lock_seen.append((run_dir / "story.lock").exists())
        launch = lc.Launch(PID, ["py", "-m", "pipeline.stages", "loop", run_id], "t")
        lc.write_launch(run_dir, launch)
        return launch


class Processes:
    def __init__(self):
        self.running = {}

    def __call__(self, pid):
        return self.running.get(pid)


@pytest.fixture
def world(tmp_path):
    repo, config, engine = project(tmp_path)
    config = config.model_copy(update={"data_dir": tmp_path})
    launcher, processes = Launcher(), Processes()
    app = create_app(config, loop_launcher=launcher, command_line=processes)
    with TestClient(app) as client:
        yield repo, config, engine, client, launcher, processes


def stopped(world):
    """A loop ended with SMT-62 stopped in its builder (no loop is running now)."""
    repo, config, engine, *_ = world
    story_loop.run_story(config, RUN, AskingStory(repo, "SMT-62", tc.STOP), engine=engine)
    return run_directory(repo, RUN)


def word_of(folder):
    """The settled word of SMT-62; it must exist."""
    word = tc.settled(folder, "SMT-62")
    assert word is not None
    return word


def go(client, key=None):
    return client.post(f"/api/runs/{RUN}/" + (f"tasks/{key}/continue" if key else "continue"))


def test_continue_takes_the_stop_back_and_starts_a_loop_when_none_is_running(world):
    repo, _, _, client, launcher, _ = world
    folder = stopped(world)
    reply = go(client, "SMT-62")
    assert reply.status_code == 200
    body = reply.json()
    assert body["continuing"] == ["SMT-62"] and body["loop_started"] is True
    assert "SMT-62 from builder" in body["detail"]
    assert launcher.calls == [RUN]
    assert tc.settled(folder, "SMT-62") is None and cont.wanted(folder, "SMT-62") == 1


def test_with_a_loop_running_only_the_note_is_left(world):
    repo, _, _, client, launcher, processes = world
    folder = stopped(world)
    lc.write_launch(folder, lc.Launch(PID, ["py"], "t"))
    processes.running[PID] = OURS
    reply = go(client, "SMT-62")
    assert reply.status_code == 200 and reply.json()["loop_started"] is False
    assert launcher.calls == [] and cont.wanted(folder, "SMT-62") == 1
    tasks = client.get(f"/api/runs/{RUN}/progress").json()["tasks"]
    assert next(t for t in tasks if t["key"] == "SMT-62")["control"] == "continuing"


def test_the_real_loop_then_finishes_the_task_in_its_own_attempt(world):
    repo, config, engine, client, *_ = world
    stopped(world)
    go(client, "SMT-62")
    result = story_loop.run_story(config, RUN, StoryRunner(), engine=engine)  # the started loop
    assert result.ok


def test_a_task_that_is_not_stopped_is_refused(world):
    _, _, _, client, launcher, _ = world
    reply = go(client, "SMT-63")
    assert reply.status_code == 409 and "not stopped" in reply.json()["detail"]
    assert launcher.calls == []


def test_a_task_of_a_running_loop_that_nobody_stopped_is_running(world):
    repo, _, _, client, _, processes = world
    lc.write_launch(run_directory(repo, RUN), lc.Launch(PID, ["py"], "t"))
    processes.running[PID] = OURS
    assert "is running now" in go(client, "SMT-62").json()["detail"]


def test_a_cancelled_task_is_final(world):
    folder = stopped(world)
    tc.settle(folder, "SMT-62", tc.CANCELLED, "builder", 1)
    reply = go(world[3], "SMT-62")
    assert reply.status_code == 409 and "cancelled" in reply.json()["detail"]


def test_a_task_still_being_stopped_must_be_waited_for(world):
    folder = stopped(world)
    tc.ask(folder, "SMT-62", tc.STOP)
    assert "still being stopped" in go(world[3], "SMT-62").json()["detail"]


def test_a_merged_task_is_done(world):
    repo, config, engine, client, *_ = world
    story_loop.run_story(config, RUN, StoryRunner(), engine=engine)
    assert "already merged" in go(client, "SMT-62").json()["detail"]


def test_an_unknown_task_is_not_found(world):
    assert go(world[3], "SMT-99").status_code == 404


def test_a_continue_whose_worktree_is_gone_is_refused_and_keeps_the_stop(world):
    repo, config, _, client, launcher, _ = world
    folder = stopped(world)
    worktree = layout.attempt_worktree(config.worktrees_dir, RUN, "SMT-62", 1)
    remove_worktree(repo, worktree, discard_changes=True)
    reply = go(client, "SMT-62")
    assert reply.status_code == 409 and "worktree is gone" in reply.json()["detail"]
    assert word_of(folder).state == tc.STOPPED and launcher.calls == []


def test_a_run_whose_budget_is_used_up_is_refused(world):
    _, _, engine, client, launcher, _ = world
    stopped(world)
    with get_session(engine) as session:
        session.query(StoryRun).filter(StoryRun.run_id == RUN).update({"budget": 0.0})
    reply = go(client, "SMT-62")
    assert reply.status_code == 409 and "budget" in reply.json()["detail"]
    assert launcher.calls == []


def test_continue_run_continues_every_stopped_task_with_one_loop(world):
    _, _, _, client, launcher, _ = world
    stopped(world)
    reply = go(client)
    assert reply.status_code == 200 and reply.json()["continuing"] == ["SMT-62"]
    assert launcher.calls == [RUN]


def test_continue_run_with_nothing_stopped_is_refused(world):
    reply = go(world[3])
    assert reply.status_code == 409 and "nothing to continue" in reply.json()["detail"]


def test_continue_run_lists_the_tasks_it_could_not_continue(world):
    repo, config, _, client, _, _ = world
    folder = stopped(world)
    tc.settle(folder, "SMT-63", tc.CANCELLED, "builder", None)
    body = go(client).json()
    assert body["continuing"] == ["SMT-62"]
    assert len(body["skipped"]) == 1 and body["skipped"][0].startswith("SMT-63: ")


def interrupted(world):
    """A loop died after the Builder and the checks of SMT-62: its process is simply gone."""
    repo, config, engine, *_ = world
    build_attempt(config, RUN, "SMT-62", TeamRunner(), 1, engine)
    for stage in ("builder", "checks"):
        checkpoint.save(repo, RUN, "SMT-62", 1, stage)
    folder = run_directory(repo, RUN)
    lc.write_launch(folder, lc.Launch(PID, ["py"], "t"))  # a launch record, and no such process
    return folder


def test_reading_the_run_marks_what_a_dead_loop_left_as_stopped(world):
    folder = interrupted(world)
    body = world[3].get(f"/api/runs/{RUN}/progress").json()
    assert body["build_state"] == "interrupted"
    task = next(t for t in body["tasks"] if t["key"] == "SMT-62")
    assert (task["control"], task["status"]) == ("stopped", "stopped")
    assert word_of(folder).stage == "tester"


def test_an_interrupted_task_is_continued_from_its_last_checkpoint(world):
    _, _, _, client, launcher, _ = world
    interrupted(world)
    reply = go(client, "SMT-62")  # nobody read the run before: Continue finds it itself
    assert reply.status_code == 200 and "SMT-62 from tester" in reply.json()["detail"]
    assert launcher.calls == [RUN]


def test_continue_clears_the_lock_a_killed_loop_left_behind(world):
    folder = interrupted(world)
    (folder / "story.lock").write_text("23644", encoding="utf-8")  # the dead loop's lock
    reply = go(world[3], "SMT-62")
    assert reply.status_code == 200
    assert world[4].lock_seen == [False]  # gone before the new loop was started
