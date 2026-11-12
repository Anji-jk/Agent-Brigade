import json

import pytest

from core.trackers.jira.story import read_story
from pipeline.planning.approval import (
    SUPERSEDED,
    ApprovalError,
    JiraWriteError,
    approve_plan,
    mark_superseded,
)
from pipeline.planning.plan_file import load_plan
from tests.pipeline.planning.planning_setup import jira_board, planned
from tests.pipeline.planning.story_samples import answer

# SMT-59 waits for both earlier sub-tasks: two links Jira does not have yet
TWO_LINKS = json.dumps(
    answer(
        SMT_59={
            "depends_on": ["SMT-57", "SMT-58"],
            "dependency_reasons": {
                "SMT-57": "It uses the formatter.",
                "SMT-58": "It documents it.",
            },
        }
    )
)


def blockers(jira, key):
    item = {i.key: i for i in read_story(jira.client(), "SMT-56", "SMT").subtasks}[key]
    return set(item.blocked_by)


def setup(tmp_path, *answers):
    result, _, repo = planned(tmp_path, *answers)
    return result.run_id, repo, jira_board()


def test_approve_writes_the_new_link_with_a_comment_and_marks_the_plan_approved(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    record = approve_plan(repo, run_id, jira.client(), "SMT")
    assert blockers(jira, "SMT-59") == {"SMT-58"}
    (link,) = [r for r in jira.requests if r[1].endswith("/issueLink")]
    assert link[2]["inwardIssue"] == {"key": "SMT-58"}  # the blocker, in Jira's own naming
    assert link[2]["outwardIssue"] == {"key": "SMT-59"} and link[2]["type"] == {"name": "Blocks"}
    assert jira.comments == [
        (
            "SMT-59",
            f"Agent Brigade (planning run {run_id}): SMT-59 waits for SMT-58. "
            "Reason: It documents the endpoint SMT-58 adds.",
        )
    ]
    approval = record["approval"]
    assert approval["status"] == "approved" and approval["approved_at"]
    assert approval["written"] == [{"subtask": "SMT-59", "blocked_by": "SMT-58", "commented": True}]
    assert approval["already_in_jira"] == []
    assert load_plan(repo, run_id)["approval"]["status"] == "approved"  # and it is on disk
    assert not [r for r in jira.requests if r[0] == "POST" and r[1].endswith("/issue")]


def test_a_link_that_is_already_in_jira_is_not_written_or_commented_again(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    jira.block("SMT-59", "SMT-58")
    approval = approve_plan(repo, run_id, jira.client(), "SMT")["approval"]
    assert approval["written"] == []
    assert approval["already_in_jira"] == [{"subtask": "SMT-59", "blocked_by": "SMT-58"}]
    assert jira.link_posts == 0 and jira.comments == []


def test_approve_twice_is_refused(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    approve_plan(repo, run_id, jira.client(), "SMT")
    with pytest.raises(ApprovalError, match="already approved"):
        approve_plan(repo, run_id, jira.client(), "SMT")
    assert jira.link_posts == 1


def test_a_stop_half_way_keeps_what_was_written_and_approving_again_carries_on(tmp_path):
    run_id, repo, jira = setup(tmp_path, TWO_LINKS)
    jira.fail_link_at = 2
    with pytest.raises(ApprovalError, match="Jira stopped the approval.*approve again"):
        approve_plan(repo, run_id, jira.client(), "SMT")
    kept = load_plan(repo, run_id)["approval"]
    assert kept["status"] == "waiting"
    assert [(w["blocked_by"], w["commented"]) for w in kept["written"]] == [("SMT-57", True)]
    jira.fail_link_at = None
    done = approve_plan(repo, run_id, jira.client(), "SMT")["approval"]
    assert done["status"] == "approved" and len(done["written"]) == 2
    assert blockers(jira, "SMT-59") == {"SMT-57", "SMT-58"}
    assert len(jira.comments) == 2 and jira.link_posts == 3  # nothing written twice


def test_a_comment_that_failed_is_added_on_the_next_try_without_a_second_link(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    jira.fail_comments = True
    with pytest.raises(ApprovalError, match="Jira stopped"):
        approve_plan(repo, run_id, jira.client(), "SMT")
    (entry,) = load_plan(repo, run_id)["approval"]["written"]
    assert entry["commented"] is False and blockers(jira, "SMT-59") == {"SMT-58"}
    jira.fail_comments = False
    approve_plan(repo, run_id, jira.client(), "SMT")
    assert jira.link_posts == 1 and len(jira.comments) == 1


def test_a_link_jira_does_not_show_afterwards_is_not_approved(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    jira.drop_links = True
    with pytest.raises(ApprovalError, match="SMT-59 is blocked by SMT-58.*not marked approved"):
        approve_plan(repo, run_id, jira.client(), "SMT")
    assert load_plan(repo, run_id)["approval"]["status"] == "waiting"


def test_a_story_that_changed_in_jira_needs_a_new_plan(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    jira.issues["SMT-59"]["fields"]["status"]["statusCategory"]["key"] = "done"
    with pytest.raises(ApprovalError, match="SMT-59 is no longer an open sub-task"):
        approve_plan(repo, run_id, jira.client(), "SMT")
    assert jira.link_posts == 0


def test_jira_being_down_changes_nothing(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    jira.down = True
    with pytest.raises(JiraWriteError, match="Jira stopped the approval"):
        approve_plan(repo, run_id, jira.client(), "SMT")
    assert load_plan(repo, run_id)["approval"]["status"] == "waiting"


def test_a_plan_without_new_links_can_still_be_approved(tmp_path):
    run_id, repo, jira = setup(tmp_path, json.dumps(answer(SMT_59={"depends_on": []})))
    record = approve_plan(repo, run_id, jira.client(), "SMT")
    assert record["approval"]["status"] == "approved" and jira.link_posts == 0


def test_a_replaced_plan_cannot_be_approved_and_is_kept(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    mark_superseded(repo, run_id, "run-new")
    kept = load_plan(repo, run_id)
    assert (
        kept["approval"]["status"] == SUPERSEDED and kept["approval"]["superseded_by"] == "run-new"
    )
    assert kept["approval"]["jira_links"]  # what it would have added is still there
    with pytest.raises(ApprovalError, match="replaced by run-new"):
        approve_plan(repo, run_id, jira.client(), "SMT")
    with pytest.raises(ApprovalError, match="replaced by run-new"):
        mark_superseded(repo, run_id, "run-other")


def test_an_approved_plan_cannot_be_marked_replaced(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    approve_plan(repo, run_id, jira.client(), "SMT")
    with pytest.raises(ApprovalError, match="already approved"):
        mark_superseded(repo, run_id, "run-new")


def test_an_unknown_run_is_named(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    with pytest.raises(ApprovalError, match="No plan found for run run-missing"):
        approve_plan(repo, "run-missing", jira.client(), "SMT")


def test_an_approved_plan_is_replaced_only_when_asked_and_keeps_what_it_wrote(tmp_path):
    run_id, repo, jira = setup(tmp_path)
    approve_plan(repo, run_id, jira.client(), "SMT")
    mark_superseded(repo, run_id, "run-new", approved_too=True)
    approval = load_plan(repo, run_id)["approval"]
    assert approval["status"] == SUPERSEDED and approval["superseded_by"] == "run-new"
    assert approval["written"] and approval["approved_at"]
