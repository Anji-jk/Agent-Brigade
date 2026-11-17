"""What an agent did, for the box under a task: its report, only the fields the page needs."""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from core.files.atomic import write_json_atomic
from pipeline.stages import story_loop as s
from pipeline.stages.stage_inputs import report_path
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import BUILDER_REPORT
from tests.pipeline.stages.test_story_loop import StoryRunner, project

TOKEN = "ghp_" + "a" * 30


@pytest.fixture
def world(tmp_path):
    repo, config, engine = project(tmp_path)
    s.run_story(config, RUN, StoryRunner(), engine=engine)
    with TestClient(create_app(config.model_copy(update={"data_dir": tmp_path}))) as client:
        yield repo, client


def report(client, stage, key="SMT-62", number=1, run=RUN):
    return client.get(f"/api/runs/{run}/tasks/{key}/attempts/{number}/report/{stage}")


def test_the_builder_box_has_what_changed_what_it_said_and_what_it_cost(world):
    _, client = world
    body = report(client, "build").json()
    assert body["exists"] is True and body["stage"] == "build"
    assert body["changed"] == ["src/a.py"]  # measured from Git, not the agent's claim
    assert body["report"] == BUILDER_REPORT
    assert body["limits"]["max_turns"] and "max_budget_usd" in body["limits"]
    assert {"turns", "cost_usd", "input_tokens", "output_tokens"} <= set(body["usage"])


def test_nothing_the_page_does_not_need_is_sent(world):
    _, client = world
    body = report(client, "build").json()
    assert "session_id" not in body["usage"]
    assert not {"worktree", "branch", "setup", "run_id"} & set(body)


def test_the_tester_and_reviewer_boxes_come_from_their_own_reports(world):
    _, client = world
    tester = report(client, "test").json()
    assert tester["summary"] == "tested it" and tester["wrote"]
    judge = report(client, "judge").json()
    assert judge["outcome"] == "done" and judge["criteria"] and judge["commit"]


def test_a_stage_that_has_not_written_yet_says_so_instead_of_failing(world):
    _, client = world
    assert report(client, "build", number=2).json() == {"stage": "build", "exists": False}


def test_a_secret_in_a_report_is_masked_before_it_leaves(world):
    repo, client = world
    path = report_path(repo, RUN, "build", "SMT-62", 1)
    write_json_atomic(path, {"ok": True, "report": f"token is {TOKEN}", "changed": []})
    body = report(client, "build").json()
    assert TOKEN not in str(body) and "[masked]" in body["report"]


def test_a_damaged_report_counts_as_not_written(world):
    repo, client = world
    report_path(repo, RUN, "build", "SMT-62", 1).write_text("{not json", encoding="utf-8")
    assert report(client, "build").json()["exists"] is False


@pytest.mark.parametrize(
    ("stage", "key", "number"),
    [("checks", "SMT-62", 1), ("nope", "SMT-62", 1), ("build", "../x", 1), ("build", "SMT-62", 0)],
)
def test_a_stage_key_or_number_that_cannot_exist_is_refused(world, stage, key, number):
    _, client = world
    assert report(client, stage, key, number).status_code in (400, 404, 422)


def test_a_run_that_does_not_exist_is_not_found(world):
    _, client = world
    assert report(client, "build", run="SMT-99-20261113-aaaa").status_code == 404
