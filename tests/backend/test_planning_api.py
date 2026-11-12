import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from core.db import get_session, make_engine
from core.db.repositories import story_runs
from core.trackers.jira.story import read_story
from pipeline.planning.plan_file import load_plan
from tests.doubles.jira import SITE
from tests.pipeline.planning.planning_setup import GOOD, jira_board, planner
from tests.pipeline.planning.story_samples import answer
from tests.pipeline.planning.test_readiness import PASS, ready_project, settings

RUN_ID = re.compile(r"SMT-56-\d{8}-[0-9a-f]{4}")
OTHER = json.dumps(answer(SMT_59={"complexity": "medium"}))


class Inline:
    """Plans at once, so a test sees the outcome without waiting."""

    def submit(self, fn, *args):
        fn(*args)


class Later:
    """Keeps the jobs until the test runs them: shows what the page sees while planning."""

    def __init__(self):
        self.jobs = []

    def submit(self, fn, *args):
        self.jobs.append((fn, args))

    def run_all(self):
        while self.jobs:
            fn, args = self.jobs.pop(0)
            fn(*args)


def make_world(tmp_path, *answers, executor=None):
    repo = ready_project(tmp_path)
    config = settings(
        tmp_path,
        project_path=repo,
        docs_dir="docs",
        test_command=PASS,
        jira_site_url=SITE,
        jira_email="a@b.c",
        jira_api_token="t",
        jira_project_key="SMT",
    )
    jira, claude = jira_board(), planner(tmp_path, *(answers or (GOOD,)))
    app = create_app(
        config,
        runner=claude,
        jira_factory=jira.client,
        claude_home=tmp_path / "claude-home",
        planning_executor=executor or Inline(),
    )
    return app, repo, config, jira, claude


@pytest.fixture
def world(tmp_path):
    app, repo, config, jira, claude = make_world(tmp_path, GOOD, OTHER, GOOD)
    with TestClient(app) as client:
        assert client.post("/api/tracker/sync").status_code == 200
        yield client, repo, jira, claude


def plan(client, budget=None, key="SMT-56"):
    body = {"budget": budget} if budget is not None else None
    response = client.post(f"/api/stories/{key}/plan", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def test_sync_and_the_tree_show_the_board(world):
    client, *_ = world
    tree = client.get("/api/tracker/tree").json()
    assert tree["space"] == "SMT" and tree["last_synced"]
    (epic,) = tree["epics"]
    assert epic["key"] == "SMT-2"
    (story,) = epic["stories"]
    assert story["key"] == "SMT-56" and story["latest_run"] is None
    assert [s["key"] for s in story["subtasks"]] == ["SMT-57", "SMT-58", "SMT-59", "SMT-60"]


def test_the_sync_answer_counts_the_board(tmp_path):
    app, *_ = make_world(tmp_path)
    with TestClient(app) as client:
        out = client.post("/api/tracker/sync").json()
    assert (out["epics"], out["stories"], out["subtasks"], out["added"]) == (1, 1, 4, 6)
    assert out["summary"].startswith("Synced SMT: 1 epics, 1 stories, 4 sub-tasks")


def test_check_runs_the_fast_checks_without_the_tests(world):
    client, *_ = world
    out = client.post("/api/stories/SMT-56/checks").json()
    assert out["ready"] and out["story_key"] == "SMT-56"
    assert out["checks"][-1]["group"] == "Tests" and out["checks"][-1]["status"] == "skipped"
    assert out["text"].startswith("Checks before planning SMT-56")


def test_plan_saves_the_run_with_its_budget_plan_branch_and_cost(world):
    client, repo, jira, claude = world
    started = plan(client, budget=12)
    run_id = started["run_id"]
    assert RUN_ID.fullmatch(run_id)
    out = client.get(f"/api/runs/{run_id}").json()
    assert out["status"] == "waiting" and out["error"] is None
    assert out["budget"] == 12.0 and out["cost"] == 0.01
    assert out["branch"] == f"agent/{run_id}"
    assert out["plan"]["run_id"] == run_id and out["plan"]["config"]["budget_usd"] == 12.0
    assert out["run_as"]["T1"].startswith("sonnet, low effort") and out["task_limits_usd"] == 3.0
    assert (repo / ".agent-brigade" / "runs" / run_id / "plan.json").is_file()
    tree = client.get("/api/tracker/tree").json()
    assert tree["epics"][0]["stories"][0]["latest_run"]["run_id"] == run_id


def test_plan_answers_at_once_and_one_run_per_story_plans_at_a_time(tmp_path):
    later = Later()
    app, *_ = make_world(tmp_path, executor=later)
    with TestClient(app) as client:
        client.post("/api/tracker/sync")
        started = plan(client)
        assert started["status"] == "planning" and started["ended_at"] is None
        again = client.post("/api/stories/SMT-56/plan")
        assert again.status_code == 409 and "already being planned" in again.text
        later.run_all()
        assert client.get(f"/api/runs/{started['run_id']}").json()["status"] == "waiting"


def test_a_story_not_on_the_board_or_a_bad_key_is_refused(tmp_path):
    app, *_ = make_world(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/stories/SMT-56/plan")  # not synced yet
        assert response.status_code == 404 and "Sync from Jira first" in response.text
        assert client.post("/api/stories/OTHER-1/plan").status_code == 400
        assert client.post("/api/stories/SMT-56/plan", json={"budget": 0}).status_code == 422
        assert client.post("/api/stories/SMT-56/plan", json={"budget": -5}).status_code == 422


def test_a_failed_readiness_check_fails_the_run_with_the_check_text(world):
    client, repo, jira, claude = world
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    run_id = plan(client)["run_id"]
    out = client.get(f"/api/runs/{run_id}").json()
    assert out["status"] == "failed" and out["plan"] is None
    assert out["error"].startswith("Checks before planning SMT-56")
    assert claude.requests == []


def test_a_refused_plan_fails_the_run_with_the_reason(tmp_path):
    app, *_ = make_world(tmp_path, "no", "no")
    with TestClient(app) as client:
        client.post("/api/tracker/sync")
        run_id = plan(client)["run_id"]
        out = client.get(f"/api/runs/{run_id}").json()
    assert out["status"] == "failed" and "refused twice" in out["error"]


def test_replan_makes_a_new_run_from_your_idea_and_the_old_one_is_superseded(world):
    client, repo, jira, claude = world
    first = plan(client, budget=12)["run_id"]
    response = client.post(f"/api/runs/{first}/replan", json={"changes": "Docs first."})
    assert response.status_code == 202, response.text
    second = response.json()
    assert second["run_id"] != first and second["budget"] == 12.0  # the budget carried over
    out = client.get(f"/api/runs/{second['run_id']}").json()
    assert out["status"] == "waiting"
    assert out["plan"]["config"]["replan"] == {"from_run": first, "changes": "Docs first."}
    listed = client.get("/api/stories/SMT-56/runs").json()
    assert [(r["run_id"], r["status"]) for r in listed] == [
        (second["run_id"], "waiting"),
        (first, "superseded"),
    ]
    assert load_plan(repo, first)["approval"]["status"] == "superseded"
    assert "--- BEGIN CHANGES ---\nDocs first." in claude.requests[-1].prompt


def test_replan_needs_an_idea_and_a_waiting_plan(world):
    client, *_ = world
    run_id = plan(client)["run_id"]
    assert client.post(f"/api/runs/{run_id}/replan", json={"changes": ""}).status_code == 422
    blank = client.post(f"/api/runs/{run_id}/replan", json={"changes": "   "})
    assert blank.status_code == 400 and "needs your idea" in blank.text
    client.post(f"/api/runs/{run_id}/approve")
    approved = client.post(f"/api/runs/{run_id}/replan", json={"changes": "x"})
    assert approved.status_code == 409 and "Plan the story again instead" in approved.text
    missing = client.post("/api/runs/SMT-56-20990101-ffff/replan", json={"changes": "x"})
    assert missing.status_code == 404


def test_approve_writes_the_links_and_one_approved_run_per_story(world):
    client, repo, jira, claude = world
    first = plan(client)["run_id"]
    out = client.post(f"/api/runs/{first}/approve").json()
    assert out["status"] == "approved" and out["plan"]["approval"]["status"] == "approved"
    item = {i.key: i for i in read_story(jira.client(), "SMT-56", "SMT").subtasks}["SMT-59"]
    assert "SMT-58" in item.blocked_by
    again = client.post(f"/api/runs/{first}/approve")
    assert again.status_code == 409
    second = plan(client)["run_id"]
    assert client.post(f"/api/runs/{second}/approve").json()["status"] == "approved"
    statuses = {r["run_id"]: r["status"] for r in client.get("/api/stories/SMT-56/runs").json()}
    assert statuses == {first: "superseded", second: "approved"}
    assert load_plan(repo, first)["approval"]["superseded_by"] == second


def test_approve_with_jira_down_keeps_the_plan_waiting(world):
    client, repo, jira, claude = world
    run_id = plan(client)["run_id"]
    jira.down = True
    response = client.post(f"/api/runs/{run_id}/approve")
    assert response.status_code == 502 and "Jira stopped the approval" in response.text
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "waiting"


def test_runs_left_planning_by_a_stop_are_failed_at_the_next_start(tmp_path):
    later = Later()
    app, repo, config, *_ = make_world(tmp_path, executor=later)
    with TestClient(app) as client:
        client.post("/api/tracker/sync")
        run_id = plan(client)["run_id"]  # never run: Brigade "stops" here
    engine = make_engine(config.db_path)
    with get_session(engine) as session:
        row = story_runs.get_run(session, 1, run_id)
        assert row is not None and row.status == "planning"
    restarted = create_app(config, runner=planner(tmp_path), planning_executor=Inline())
    with TestClient(restarted) as client:
        out = client.get(f"/api/runs/{run_id}").json()
    assert out["status"] == "failed" and "stopped while this run was planning" in out["error"]
    engine.dispose()


def test_an_unknown_run_is_404(world):
    client, *_ = world
    assert client.get("/api/runs/SMT-56-20990101-ffff").status_code == 404
