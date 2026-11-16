import json

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from pipeline.stages import attempt_log
from pipeline.stages import story_loop as s
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.test_story_loop import StoryRunner, project

TOKEN = "ghp_" + "a" * 30


def make_client(tmp_path, *, run=True):
    repo, config, engine = project(tmp_path)
    if run:
        s.run_story(config, RUN, StoryRunner(), engine=engine)
    app = create_app(config.model_copy(update={"data_dir": tmp_path}))
    return repo, TestClient(app)


@pytest.fixture
def world(tmp_path):
    repo, client = make_client(tmp_path)
    with client:
        yield repo, client


def test_progress_lists_every_task_with_its_attempts_agents_cost_and_merge(world):
    _, client = world
    body = client.get(f"/api/runs/{RUN}/progress").json()
    assert (body["run_id"], body["story_key"], body["status"]) == (RUN, "SMT-61", "approved")
    first, second = body["tasks"]
    assert (first["key"], second["key"]) == ("SMT-62", "SMT-63")
    assert second["depends_on"] == ["SMT-62"] and first["depends_on"] == []
    assert (first["status"], first["stage"]) == ("done", "merged")
    (attempt,) = first["attempts"]
    assert attempt["number"] == 1 and attempt["outcome"] == "done"
    assert attempt["merge"]["kind"] == "fast-forward"
    assert {a["role"] for a in attempt["agents"]} >= {"builder", "reviewer"}
    assert attempt["sources"] == ["orchestrator"]
    assert first["cost"] == pytest.approx(sum(a["cost"] for a in attempt["agents"]))
    assert body["cost"] == pytest.approx(first["cost"] + second["cost"])


def test_a_task_that_has_not_started_is_waiting_with_no_attempts(tmp_path):
    _, client = make_client(tmp_path, run=False)
    with client:
        body = client.get(f"/api/runs/{RUN}/progress").json()
    assert [t["key"] for t in body["tasks"]] == ["SMT-62", "SMT-63"]
    assert all(t["status"] == "waiting" and t["attempts"] == [] for t in body["tasks"])
    assert body["cost"] == 0


def test_the_titles_come_from_the_plan(world):
    _, client = world
    tasks = client.get(f"/api/runs/{RUN}/progress").json()["tasks"]
    assert all(t["title"] for t in tasks)


@pytest.mark.parametrize("run_id", ["SMT-61-20990101-ffff", "not-a-run"])
def test_a_run_that_is_not_in_the_project_is_not_found(world, run_id):
    _, client = world
    for path in ("progress", "log", "tasks/SMT-62/attempts/1/events"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 404


def test_the_story_log_is_a_feed_that_can_be_asked_for_from_a_point(world):
    _, client = world
    whole = client.get(f"/api/runs/{RUN}/log").json()
    assert whole["items"][0]["title"].startswith("story started")
    assert whole["items"][-1]["title"] == "story finished"
    assert (whole["from"], whole["next"], whole["count"]) == (
        0,
        whole["count"],
        len(whole["items"]),
    )
    rest = client.get(f"/api/runs/{RUN}/log", params={"after": whole["count"] - 1}).json()
    assert [i["title"] for i in rest["items"]] == ["story finished"]


def test_one_source_of_an_attempt_is_a_feed_that_names_the_sources_it_has(world):
    _, client = world
    body = client.get(f"/api/runs/{RUN}/tasks/SMT-62/attempts/1/events").json()
    titles = [i["title"] for i in body["items"]]
    assert titles[0] == "attempt 1 started" and "merge into the story branch" in titles
    assert body["sources"] == ["orchestrator"]


def test_an_attempt_that_has_not_started_has_an_empty_feed(world):
    _, client = world
    body = client.get(f"/api/runs/{RUN}/tasks/SMT-62/attempts/5/events").json()
    assert body["items"] == [] and body["sources"] == []


@pytest.mark.parametrize(
    "path",
    [
        "tasks/SMT-62/attempts/1/events?source=judge",
        "tasks/SMT-62/attempts/0/events",
        "tasks/smt-62/attempts/1/events",
        "tasks/SMT-62/attempts/x/events",
    ],
)
def test_a_source_key_or_number_that_cannot_exist_is_refused(world, path):
    _, client = world
    assert client.get(f"/api/runs/{RUN}/{path}").status_code in (400, 422)


def write_builder_stream(repo):
    path = attempt_log.agent_events_path(repo, RUN, "SMT-62", 1, "builder")
    call = {
        "type": "assistant",
        "message": {
            "id": "m",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cat .env"}}
            ],
        },
    }
    out = "\n".join([f"GITHUB_TOKEN={TOKEN}1"] + [f"line {n}" for n in range(300)])
    back = {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": out}]},
    }
    path.write_text("\n".join(json.dumps(x) for x in (call, back)) + "\n", encoding="utf-8")


def test_an_agents_stream_is_shown_masked_and_cut_and_whole_only_when_asked(world):
    repo, client = world
    write_builder_stream(repo)
    url = f"/api/runs/{RUN}/tasks/SMT-62/attempts/1/events"
    short = client.get(url, params={"source": "builder"})
    assert TOKEN not in short.text and "[masked]" in short.text
    assert "lines hidden" in short.text
    assert "builder" in short.json()["sources"]
    whole = client.get(url, params={"source": "builder", "full": "true"})
    assert TOKEN not in whole.text and "lines hidden" not in whole.text and "line 299" in whole.text
