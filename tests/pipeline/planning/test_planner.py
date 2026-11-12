import json

import pytest

from pipeline.planning import planner as p
from pipeline.planning.plan_file import load_plan
from pipeline.planning.planner_limits import planner_limits
from pipeline.runner.claude_runner import AgentError
from tests.pipeline.planning.planning_setup import GOOD, planned, planner, project
from tests.pipeline.planning.story_samples import ANSWER, answer, story, work_item
from tests.pipeline.workspace.repo import git


def test_a_good_answer_is_saved_as_the_plan(tmp_path):
    result, fake, repo = planned(tmp_path)
    assert result.path == repo / ".agent-brigade" / "runs" / result.run_id / "plan.json"
    record = load_plan(repo, result.run_id)
    assert [t["jira_key"] for t in record["tasks"]] == ["SMT-57", "SMT-58", "SMT-59"]
    assert record["source"]["key"] == "SMT-56" and record["source"]["epic"]["key"] == "SMT-2"
    assert record["approval"] == {
        "status": "waiting",
        "jira_links": result.record["approval"]["jira_links"],
    }
    assert record["skipped_subtasks"] == [{"key": "SMT-60", "status": "Done"}]
    config = record["config"]
    assert config["branch"] == f"agent/{result.run_id}"
    assert config["base_ref"] == "main" and config["base_commit"] == git(repo, "rev-parse", "HEAD")
    assert config["model"] == "opus" and config["docs_dir"] == "docs"
    assert record["planner"]["rounds"] == 1 and record["planner"]["total_cost_usd"] == 0.01
    assert git(repo, "status", "--porcelain") == ""  # .agent-brigade/ is ignored
    assert git(repo, "branch", "--list").strip() == "* main"  # the branch is only named


def test_the_planner_is_read_only_in_the_project_and_cannot_read_secrets(tmp_path):
    result, fake, repo = planned(tmp_path)
    (request,) = fake.requests
    assert request.agent == "planner" and request.cwd == p.REPO_ROOT
    assert request.tools == ("Read", "Grep", "Glob")
    assert request.add_dirs == (repo.resolve(),)
    assert not request.resume and request.allowed_bash == ()
    rules = " ".join(request.deny)
    for part in ("/**/.env)", "/**/.env.*)", "/.agent-brigade/**)"):
        assert part in rules
    assert request.prompt.startswith("Plan the story SMT-56.")
    assert "README.md" in request.prompt and "CLAUDE.md" in request.prompt  # tracked files


def test_a_refused_answer_is_sent_back_once_in_the_same_session(tmp_path):
    twice = json.dumps(answer(SMT_57={"complexity": "huge"}))
    result, fake, repo = planned(tmp_path, twice, GOOD)
    first, second = fake.requests
    assert second.resume and second.session_id == first.session_id
    assert second.prompt.startswith("[Message from the Brigade system]")
    assert "complexity must be one of" in second.prompt
    assert result.record["planner"]["rounds"] == 2
    assert result.record["planner"]["total_cost_usd"] == pytest.approx(0.02)


@pytest.mark.parametrize("bad", ["not json at all", json.dumps({"tasks": []})])
def test_an_answer_refused_twice_saves_nothing(tmp_path, bad):
    with pytest.raises(p.PlanningError, match="refused twice"):
        planned(tmp_path, bad, bad)
    assert not (tmp_path / "proj" / ".agent-brigade").exists()


def test_a_planner_that_changes_the_project_saves_nothing(tmp_path):
    def writes_a_file(request):
        (tmp_path / "proj" / "sneaky.py").write_text("x", encoding="utf-8")
        return GOOD

    with pytest.raises(p.PlanningError, match="Git state changed"):
        planned(tmp_path, writes_a_file)
    assert not (tmp_path / "proj" / ".agent-brigade").exists()


def test_a_planner_that_fails_is_reported(tmp_path):
    with pytest.raises(p.PlanningError, match="planner agent stopped: error_max_turns"):
        planned(tmp_path, AgentError("The planner agent stopped: error_max_turns"))


def test_a_failed_readiness_check_stops_before_the_planner(tmp_path):
    repo, settings = project(tmp_path)
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    fake = planner(tmp_path, GOOD)
    with pytest.raises(p.NotReady) as caught:
        p.plan_story(story(), settings, fake)
    assert caught.value.checks.failed and fake.requests == []


def test_a_subtask_without_criteria_stops_before_anything_runs(tmp_path):
    repo, settings = project(tmp_path)
    fake = planner(tmp_path, GOOD)
    no_criteria = story(work_item("SMT-57", "a", criteria=""))
    with pytest.raises(p.PlanningError, match="No acceptance criteria in SMT-57"):
        p.plan_story(no_criteria, settings, fake)
    assert fake.requests == []


def test_a_run_id_is_used_once(tmp_path):
    repo, settings = project(tmp_path)
    p.plan_story(story(), settings, planner(tmp_path, GOOD), run_id="run-1")
    with pytest.raises(p.PlanningError, match="already exists for run run-1"):
        p.plan_story(story(), settings, planner(tmp_path, GOOD), run_id="run-1", run_tests=False)


def test_a_docs_folder_counts_only_when_the_project_has_it(tmp_path):
    (tmp_path / "docs").mkdir()
    assert p.docs_folder(tmp_path, "docs") == "docs"
    assert p.docs_folder(tmp_path, "manual") == ""
    assert p.docs_folder(tmp_path, "") == ""


def test_without_a_docs_folder_doc_targets_are_left_out(tmp_path):
    repo, settings = project(tmp_path)
    settings = settings.model_copy(update={"docs_dir": "manual"})
    result = p.plan_story(story(), settings, planner(tmp_path, GOOD))
    assert result.record["tasks"][0]["doc_target"] is None
    assert result.record["config"]["docs_dir"] is None
    assert ANSWER["tasks"][0]["doc_target"] == "docs/export.md"  # the Planner did give one


def test_the_limits_come_from_the_table_not_from_code(tmp_path):
    result, fake, repo = planned(tmp_path)
    (request,) = fake.requests
    limits = planner_limits()
    assert request.max_turns == limits.max_turns
    assert request.max_budget_usd == limits.max_budget_usd
    assert request.timeout == limits.timeout_seconds
    assert result.record["planner"]["max_turns"] == limits.max_turns
    assert result.record["config"]["timeout_seconds"] == limits.timeout_seconds


def test_a_story_budget_is_saved_shown_to_the_planner_and_lowers_its_cap(tmp_path):
    result, fake, repo = planned(tmp_path, budget=2)
    assert result.record["config"]["budget_usd"] == 2.0
    assert result.record["planner"]["max_budget_usd"] == 2.0
    (request,) = fake.requests
    assert request.max_budget_usd == 2.0
    assert "Story budget: $2 for planning and building this story together" in request.prompt


def test_a_big_story_budget_never_raises_the_planners_own_cap(tmp_path):
    result, fake, repo = planned(tmp_path, budget=500)
    assert fake.requests[0].max_budget_usd == planner_limits().max_budget_usd
    assert result.record["config"]["budget_usd"] == 500.0


def test_without_a_budget_none_is_saved(tmp_path):
    result, fake, repo = planned(tmp_path)
    assert result.record["config"]["budget_usd"] is None
    assert result.record["config"]["replan"] is None
    assert "Story budget: none set" in fake.requests[0].prompt


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), "5", True])
def test_a_budget_that_is_not_a_positive_amount_is_refused(tmp_path, bad):
    repo, settings = project(tmp_path)
    fake = planner(tmp_path, GOOD)
    with pytest.raises(p.PlanningError, match="budget"):
        p.plan_story(story(), settings, fake, budget=bad)
    assert fake.requests == []


def test_a_fix_round_gets_only_the_money_that_is_left(tmp_path):
    refused = json.dumps(answer(SMT_57={"complexity": "huge"}))
    result, fake, repo = planned(tmp_path, refused, GOOD, budget=1)
    first, second = fake.requests
    assert first.max_budget_usd == 1.0
    assert second.max_budget_usd == pytest.approx(0.99)


def test_no_second_round_starts_when_the_money_is_used_up(tmp_path):
    refused = json.dumps(answer(SMT_57={"complexity": "huge"}))
    with pytest.raises(p.PlanningError, match=r"\$0.05 spending limit"):
        planned(tmp_path, refused, GOOD, budget=0.05)
