import json
from dataclasses import replace

import pytest

from pipeline.planning.approval import approve_plan
from pipeline.planning.plan_file import load_plan
from pipeline.planning.planner import PlanningError, plan_story
from pipeline.planning.replan import replan_story
from tests.pipeline.planning.planning_setup import GOOD, jira_board, planner, project
from tests.pipeline.planning.story_samples import answer, story

REORDERED = json.dumps(answer(SMT_59={"files": ["docs/first.md"], "complexity": "medium"}))


def first_plan(tmp_path, **options):
    repo, settings = project(tmp_path)
    fake = planner(tmp_path, GOOD, REORDERED, GOOD)
    return repo, settings, fake, plan_story(story(), settings, fake, **options)


def test_a_replan_is_a_new_run_made_from_the_old_one_and_your_idea(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path)
    second = replan_story(story(), settings, fake, first.run_id, "  Put the docs first.  ")
    assert second.run_id != first.run_id
    assert second.record["tasks"][2]["complexity"] == "medium"  # the new answer, not the old
    assert second.record["config"]["replan"] == {
        "from_run": first.run_id,
        "changes": "Put the docs first.",
    }
    prompt = fake.requests[-1].prompt
    assert f"## Your previous plan (run {first.run_id})" in prompt
    assert "--- BEGIN CHANGES ---\nPut the docs first.\n--- END CHANGES ---" in prompt
    assert not fake.requests[-1].resume  # a new conversation, not the old session


def test_the_old_plan_is_kept_and_marked_replaced(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path)
    before = load_plan(repo, first.run_id)
    second = replan_story(story(), settings, fake, first.run_id, "Docs first.")
    old = load_plan(repo, first.run_id)
    assert old["approval"]["status"] == "superseded"
    assert old["approval"]["superseded_by"] == second.run_id
    assert {**old, "approval": None} == {**before, "approval": None}  # nothing else changed
    assert load_plan(repo, second.run_id)["approval"]["status"] == "waiting"


def test_the_budget_carries_over_unless_a_new_one_is_given(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path, budget=12)
    second = replan_story(story(), settings, fake, first.run_id, "Docs first.")
    assert second.record["config"]["budget_usd"] == 12.0
    third = replan_story(story(), settings, fake, second.run_id, "Smaller.", budget=3)
    assert third.record["config"]["budget_usd"] == 3.0
    assert "Story budget: $3 for planning" in fake.requests[-1].prompt


def test_a_replan_needs_your_idea(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path)
    for empty in ("", "   ", None):
        with pytest.raises(PlanningError, match="needs your idea"):
            replan_story(story(), settings, fake, first.run_id, empty)  # type: ignore[arg-type]
    assert len(fake.requests) == 1  # the Planner was not asked again


def test_an_approved_plan_cannot_be_replanned(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path)
    approve_plan(repo, first.run_id, jira_board().client(), "SMT")
    with pytest.raises(PlanningError, match="already approved.*Plan the story again"):
        replan_story(story(), settings, fake, first.run_id, "Docs first.")
    assert len(fake.requests) == 1


def test_a_replaced_plan_cannot_be_replanned_again(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path)
    second = replan_story(story(), settings, fake, first.run_id, "Docs first.")
    with pytest.raises(PlanningError, match=f"replaced by {second.run_id}.*re-plan that run"):
        replan_story(story(), settings, fake, first.run_id, "Another idea.")


def test_a_refused_replan_leaves_the_old_plan_waiting(tmp_path):
    repo, settings = project(tmp_path)
    fake = planner(tmp_path, GOOD, "no", "no")
    first = plan_story(story(), settings, fake)
    with pytest.raises(PlanningError, match="refused twice"):
        replan_story(story(), settings, fake, first.run_id, "Docs first.")
    assert load_plan(repo, first.run_id)["approval"]["status"] == "waiting"
    assert len(list((repo / ".agent-brigade" / "runs").iterdir())) == 1


def test_a_plan_of_another_story_or_a_missing_run_is_named(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path)
    other = replace(story(), story=replace(story().story, key="SMT-99"))
    with pytest.raises(PlanningError, match="plan for SMT-56, not for SMT-99"):
        replan_story(other, settings, fake, first.run_id, "Docs first.")
    with pytest.raises(PlanningError, match="No plan found for run run-missing"):
        replan_story(story(), settings, fake, "run-missing", "Docs first.")


def test_a_replan_needs_a_project(tmp_path):
    repo, settings, fake, first = first_plan(tmp_path)
    nowhere = settings.model_copy(update={"project_path": None})
    with pytest.raises(PlanningError, match="BRIGADE_PROJECT_PATH is empty"):
        replan_story(story(), nowhere, fake, first.run_id, "Docs first.")
