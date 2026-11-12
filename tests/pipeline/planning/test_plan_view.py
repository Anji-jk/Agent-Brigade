import json

from pipeline.planning.plan_view import format_plan
from tests.pipeline.planning.planning_setup import planned
from tests.pipeline.planning.story_samples import answer


def test_the_plan_reads_like_the_planning_screen(tmp_path):
    result, _, _ = planned(tmp_path)
    text = format_plan(result.record, "plan.json")
    assert text.startswith("Plan for story SMT-56 - Export a person's skills\nEpic:        SMT-2")
    assert f"Branch:      agent/{result.run_id} (from main at " in text
    assert "Model:       opus" in text
    assert "Summary:     Formatter first" in text
    assert "Tasks (3), in Jira's order:" in text
    assert "  T2  SMT-58  Add the export endpoint" in text
    assert "      Needs:   T1 (SMT-57): Jira: SMT-58 is blocked by SMT-57\n" in text
    assert (
        "      Needs:   T2 (SMT-58): It documents the endpoint SMT-58 adds. "
        "[new: added to Jira after approval]"
    ) in text
    assert "      Run as:  small, one at a time -> sonnet, low effort, 10 turns" in text
    assert "      Accept:  Commas in names are quoted." in text
    assert "      Doc:     docs/export.md" in text
    assert "      Read:    CLAUDE.md, backend/models.py" in text
    assert "      Notes:   Use csv." in text
    assert "Left out, done in Jira: SMT-60 (Done)" in text
    assert "Jira changes after approval (1):\n  + SMT-59 is blocked by SMT-58" in text
    assert "Status:      waiting for approval" in text
    assert "Planner:     duration s 1.5, cost USD 0.0100, turns 3, rounds 1" in text
    assert text.endswith("Plan file:   plan.json")


def test_notes_no_links_and_approval_are_shown(tmp_path):
    shared = answer(
        SMT_57={"parallel_safe": True, "files": ["README.md"]},
        SMT_59={
            "parallel_safe": True,
            "depends_on": [],
            "dependency_reasons": {},
            "files": ["README.md"],
        },
    )
    result, _, _ = planned(tmp_path, json.dumps(shared))
    record = {
        **result.record,
        "approval": {"status": "approved", "approved_at": "today", "jira_links": []},
    }
    text = format_plan(record, "p")
    assert (
        "What Brigade changed in the Planner's answer:\n  - T1 (SMT-57) runs one at a time" in text
    )
    assert "  none: every dependency is already a Jira link" in text
    assert "Status:      approved today" in text
    assert "Needs:   nothing" in text


def test_without_a_budget_the_view_says_so_and_adds_up_the_task_limits(tmp_path):
    result, _, _ = planned(tmp_path)
    text = format_plan(result.record, "p")
    assert "Budget:      none set (the tasks' limits add up to $3)" in text


def test_a_budget_shows_what_planning_used_and_what_is_left(tmp_path):
    result, _, _ = planned(tmp_path, budget=12)
    text = format_plan(result.record, "p")
    assert "Budget:      $12 for planning and building this story\n" in text
    assert "planning used $0.01, so $11.99 is left; the tasks' limits add up to $3\n" in text
    assert "Warning" not in text


def test_a_budget_smaller_than_the_task_limits_gets_a_warning(tmp_path):
    result, _, _ = planned(tmp_path, budget=2)
    text = format_plan(result.record, "p")
    assert "Warning: the task limits add up to more than what is left" in text


def test_a_replan_and_a_replaced_plan_are_shown(tmp_path):
    result, _, _ = planned(tmp_path)
    replanned = {
        **result.record,
        "config": {
            **result.record["config"],
            "replan": {"from_run": "run-1", "changes": "Docs first,\n  then the endpoint."},
        },
        "approval": {"status": "superseded", "superseded_by": "run-2", "jira_links": []},
    }
    text = format_plan(replanned, "p")
    assert "Re-plan of:  run-1\nChanges:     Docs first, then the endpoint.\n" in text
    assert "Status:      replaced by run-2" in text
