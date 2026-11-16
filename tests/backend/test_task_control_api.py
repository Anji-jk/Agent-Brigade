import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from core.runs import run_directory
from pipeline.control import launch as lc
from pipeline.control import task_control as tc
from pipeline.stages import story_loop
from pipeline.stages.attempt_log import attempt_dir
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.test_story_loop import StoryRunner, project

PID = 4242
OURS = f"python -m pipeline.stages loop {RUN}"


class Processes:
    def __init__(self):
        self.running = {PID: OURS}

    def __call__(self, pid):
        return self.running.get(pid)


@pytest.fixture
def world(tmp_path):
    repo, config, _ = project(tmp_path)
    config = config.model_copy(update={"data_dir": tmp_path})
    processes = Processes()
    app = create_app(config, command_line=processes)
    with TestClient(app) as client:
        yield repo, config, client, processes, app


def loop_running(repo):
    lc.write_launch(run_directory(repo, RUN), lc.Launch(PID, ["py", "-m", "x"], "t"))


def working_on(repo, key="SMT-62", number=1):
    """What the loop leaves the moment a task's attempt begins: its folder."""
    attempt_dir(repo, RUN, key, number).mkdir(parents=True)


def post(client, what, key=None):
    tail = f"/tasks/{key}/{what}" if key else f"/{what}"
    return client.post(f"/api/runs/{RUN}{tail}")


def control_of(client, key):
    tasks = client.get(f"/api/runs/{RUN}/progress").json()["tasks"]
    return next(t["control"] for t in tasks if t["key"] == key)


def test_stop_leaves_a_request_for_the_loop_and_progress_says_stopping(world):
    repo, _, client, _, _ = world
    loop_running(repo)
    working_on(repo)
    reply = post(client, "stop", "SMT-62")
    assert reply.status_code == 200
    assert (reply.json()["state"], reply.json()["key"]) == ("stopping", "SMT-62")
    assert tc.pending(run_directory(repo, RUN), "SMT-62") == tc.STOP
    assert control_of(client, "SMT-62") == "stopping" and control_of(client, "SMT-63") is None


def test_a_second_stop_while_it_is_being_stopped_is_refused(world):
    repo, _, client, _, _ = world
    loop_running(repo)
    working_on(repo)
    post(client, "stop", "SMT-62")
    again = post(client, "stop", "SMT-62")
    assert again.status_code == 409 and "already being stopped" in again.json()["detail"]


def test_a_task_that_is_not_running_cannot_be_stopped(world):
    repo, _, client, _, _ = world
    loop_running(repo)  # a loop is working, but nothing has begun on SMT-62
    reply = post(client, "stop", "SMT-62")
    assert reply.status_code == 409 and "not running now" in reply.json()["detail"]
    assert tc.pending(run_directory(repo, RUN), "SMT-62") is None


def test_a_task_cannot_be_stopped_when_no_loop_is_working(world):
    repo, _, client, _, _ = world
    working_on(repo)  # a folder from an earlier run, but no loop
    reply = post(client, "stop", "SMT-62")
    assert reply.status_code == 409 and "no loop working" in reply.json()["detail"]


def test_a_task_the_plan_does_not_have_is_not_found(world):
    _, _, client, _, _ = world
    assert post(client, "stop", "SMT-99").status_code == 404
    assert post(client, "cancel", "SMT-99").status_code == 404
    assert client.post("/api/runs/SMT-61-20990101-ffff/tasks/SMT-62/stop").status_code == 404


def test_cancel_of_a_running_task_leaves_a_cancel_the_loop_acts_on(world):
    repo, _, client, _, _ = world
    loop_running(repo)
    working_on(repo)
    reply = post(client, "cancel", "SMT-62")
    assert reply.status_code == 200 and reply.json()["state"] == "cancelling"
    assert tc.pending(run_directory(repo, RUN), "SMT-62") == tc.CANCEL
    assert control_of(client, "SMT-62") == "cancelling"
    assert post(client, "cancel", "SMT-62").status_code == 409


def test_a_cancel_overtakes_a_stop_that_was_still_on_its_way(world):
    repo, _, client, _, _ = world
    loop_running(repo)
    working_on(repo)
    post(client, "stop", "SMT-62")
    assert post(client, "cancel", "SMT-62").json()["state"] == "cancelling"
    assert tc.pending(run_directory(repo, RUN), "SMT-62") == tc.CANCEL


def test_with_no_loop_working_a_cancel_is_settled_at_once_and_is_final(world):
    repo, _, client, _, _ = world
    reply = post(client, "cancel", "SMT-63")
    assert reply.status_code == 200 and reply.json()["state"] == "cancelled"
    assert "worktree and branch are kept" in reply.json()["detail"]
    assert tc.settled(run_directory(repo, RUN), "SMT-63").state == tc.CANCELLED
    assert control_of(client, "SMT-63") == "cancelled"
    assert "final" in post(client, "cancel", "SMT-63").json()["detail"]
    assert post(client, "stop", "SMT-63").status_code == 409


def test_a_stopped_task_can_still_be_cancelled_even_while_a_loop_works(world):
    repo, _, client, _, _ = world
    loop_running(repo)
    tc.settle(run_directory(repo, RUN), "SMT-62", tc.STOPPED, "tester", 1)
    assert post(client, "stop", "SMT-62").status_code == 409  # already stopped
    reply = post(client, "cancel", "SMT-62")
    assert reply.status_code == 200 and reply.json()["state"] == "cancelled"
    assert tc.settled(run_directory(repo, RUN), "SMT-62").state == tc.CANCELLED


def test_a_merged_task_is_done_and_can_be_neither_stopped_nor_cancelled(world):
    repo, config, client, _, app = world
    assert story_loop.run_story(config, RUN, StoryRunner(), engine=app.state.engine).ok
    for what in ("stop", "cancel"):
        reply = post(client, what, "SMT-62")
        assert reply.status_code == 409 and "already merged" in reply.json()["detail"]


def test_stop_all_asks_every_running_task_and_names_them(world):
    repo, _, client, _, _ = world
    loop_running(repo)
    working_on(repo, "SMT-62")
    working_on(repo, "SMT-63")
    reply = post(client, "stop")
    assert reply.status_code == 200 and reply.json()["stopping"] == ["SMT-62", "SMT-63"]
    folder = run_directory(repo, RUN)
    assert [tc.pending(folder, k) for k in ("SMT-62", "SMT-63")] == [tc.STOP, tc.STOP]


def test_stop_all_skips_what_is_not_running_and_refuses_when_nothing_is(world):
    repo, _, client, _, _ = world
    loop_running(repo)
    assert post(client, "stop").status_code == 409  # nothing is running
    working_on(repo, "SMT-63")
    assert post(client, "stop").json()["stopping"] == ["SMT-63"]
    assert post(client, "stop").status_code == 409  # already on its way


def test_a_key_made_of_path_pieces_never_reaches_the_disk(world):
    _, _, client, _, _ = world
    reply = client.post(f"/api/runs/{RUN}/tasks/..%2F..%2Fx/stop")
    assert reply.status_code in (404, 405)
