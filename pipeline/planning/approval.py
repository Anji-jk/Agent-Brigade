"""Approve a plan, and mark a plan replaced by a re-plan.

Approve writes the dependencies the Planner added to Jira, and nothing else:

* each one as an "is blocked by" link between two sub-tasks, followed by a comment on the blocked
  sub-task giving the reason and the run (a comment sent with the link would land on the blocker);
* a link that is already in Jira is not written twice, and its comment is not repeated;
* after every write the plan's ``approval`` block records what was done, so a stop half-way
  keeps it and approving again carries on from there;
* at the end every link is read back from Jira. Only then does the plan say ``approved``.

Git is not touched. A plan that is approved or replaced can no longer be approved.
"""

from pathlib import Path
from typing import Any

from core.runs import utc_now
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from core.trackers.jira.story import read_story
from pipeline.planning.plan_file import PlanFileError, load_plan, save_approval
from pipeline.planning.story_plan import APPROVED

SUPERSEDED = "superseded"


class ApprovalError(Exception):
    """The plan could not be approved or marked replaced; the message says why."""


class JiraWriteError(ApprovalError):
    """Jira could not be read or written; what was done is kept, so approving again goes on."""


def _pair(link: dict[str, Any]) -> tuple[str, str]:
    return link["subtask"], link["blocked_by"]


def _waiting(record: dict[str, Any], run_id: str) -> dict[str, Any]:
    """The plan's approval block, if the plan is still waiting for a decision."""
    approval = record.get("approval") or {}
    if approval.get("status") == APPROVED:
        raise ApprovalError(f"Run {run_id} is already approved.")
    if approval.get("status") == SUPERSEDED:
        raise ApprovalError(
            f"Run {run_id} was replaced by {approval.get('superseded_by')}: use that plan."
        )
    return approval


def mark_superseded(
    project_root: Path, run_id: str, new_run_id: str, *, approved_too: bool = False
) -> None:
    """Keep the old plan, but say that `new_run_id` replaces it.

    `approved_too`: an approved plan may be replaced as well (another plan of the same story was
    approved; one approved plan per story). Its record of what was written to Jira is kept.
    """
    record = load_plan(project_root, run_id)
    approval = record.get("approval") or {}
    if not (approved_too and approval.get("status") == APPROVED):
        approval = _waiting(record, run_id)
    save_approval(
        project_root,
        run_id,
        {**approval, "status": SUPERSEDED, "superseded_by": new_run_id, "superseded_at": utc_now()},
    )


def _comment(run_id: str, link: dict[str, Any]) -> str:
    return (
        f"Agent Brigade (planning run {run_id}): {link['subtask']} waits for "
        f"{link['blocked_by']}. Reason: {link['reason']}"
    )


def _check(record: dict[str, Any], story: Any) -> None:
    """Every link must still join two open sub-tasks of the story."""
    open_keys = {item.key for item in story.open_subtasks()}
    for link in record["approval"].get("jira_links") or []:
        gone = [key for key in _pair(link) if key not in open_keys]
        if gone:
            raise ApprovalError(
                f"{', '.join(gone)} is no longer an open sub-task of {story.story.key}: "
                "the story changed in Jira since this plan. Plan the story again."
            )


def approve_plan(
    project_root: Path, run_id: str, client: JiraClient, space: str | None = None
) -> dict[str, Any]:
    """Write the plan's new dependencies to Jira, read them back, and mark the plan approved."""
    try:
        record = load_plan(project_root, run_id)
        approval = _waiting(record, run_id)
        links = approval.get("jira_links") or []
        key = record["source"]["key"]
        story = read_story(client, key, space)
        _check(record, story)
        written = [dict(entry) for entry in approval.get("written") or []]
        by_pair = {_pair(entry): entry for entry in written}
        blocked_by = {item.key: item.blocked_by for item in story.subtasks}
        already: list[dict[str, str]] = []
        for link in links:
            pair, entry = _pair(link), by_pair.get(_pair(link))
            if entry is None and link["blocked_by"] in blocked_by[link["subtask"]]:
                already.append({"subtask": pair[0], "blocked_by": pair[1]})
                continue
            if entry is None:
                client.add_blocks_link(link["blocked_by"], link["subtask"])
                entry = {"subtask": pair[0], "blocked_by": pair[1], "commented": False}
                written.append(entry)
                by_pair[pair] = entry
                save_approval(project_root, run_id, {**approval, "written": written})
            if not entry["commented"]:
                client.add_comment(link["subtask"], _comment(run_id, link))
                entry["commented"] = True
                save_approval(project_root, run_id, {**approval, "written": written})
        seen = {item.key: item.blocked_by for item in read_story(client, key, space).subtasks}
        missing = [f"{a} is blocked by {b}" for a, b in map(_pair, links) if b not in seen[a]]
        if missing:
            raise ApprovalError(
                f"Jira does not show these links after writing them: {'; '.join(missing)}. "
                "The plan was not marked approved."
            )
        return save_approval(
            project_root,
            run_id,
            {
                **approval,
                "status": APPROVED,
                "approved_at": utc_now(),
                "written": written,
                "already_in_jira": already,
            },
        )
    except TrackerError as exc:
        raise JiraWriteError(
            f"Jira stopped the approval: {exc} What was written is kept in the plan; "
            "approve again to carry on."
        ) from None
    except PlanFileError as exc:
        raise ApprovalError(str(exc)) from None
