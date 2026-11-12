"""A story's plan: Jira's fields, the planner's choices, and the checks that join them.

``merge_planner_output`` takes the planner's answer and the story. It copies the Jira-owned
fields (story_tasks) unchanged and takes only PLANNER_FIELDS from the planner. The planner may
add dependencies, each with a reason, but cannot remove a Jira "is blocked by" link: those are
always kept. Added dependencies become Jira links, written only when a person approves.

Nothing here reads or writes Jira, Git or files.
"""

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from core.trackers.models import Story, WorkItem
from pipeline.planning.plan_fields import PlanValidationError
from pipeline.planning.plan_file import validate_tasks
from pipeline.planning.story_tasks import jira_tasks

WAITING, APPROVED = "waiting", "approved"
PLANNER_FIELDS = (
    "files",
    "depends_on",
    "dependency_reasons",
    "parallel_safe",
    "complexity",
    "expected_outcome",
    "verification",
    "doc_target",
    "context",
)


def _jira_reason(item: WorkItem, blocker: str) -> str:
    return f"Jira: {item.key} is blocked by {blocker}"


def _inside(path: str, folder: str) -> bool:
    return PurePosixPath(path.replace("\\", "/")).as_posix().startswith(folder + "/")


@dataclass
class _Review:
    """What checking the planner's answer found for one story."""

    story: Story
    by_key: dict[str, dict[str, Any]]  # open sub-task key -> its Jira-owned task
    done: set[str]  # sub-tasks already done in Jira
    problems: list[str] = field(default_factory=list)  # any one refuses the answer
    notes: list[str] = field(default_factory=list)  # what code changed, shown with the plan
    jira_links: list[dict[str, str]] = field(default_factory=list)  # written on Approve


def _answers(review: _Review, raw_tasks: list[Any]) -> dict[str, dict[str, Any]]:
    """The planner's entries by sub-task key; entries it cannot use are reported."""
    answers: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_tasks, 1):
        key = raw.get("key") if isinstance(raw, dict) else None
        if not isinstance(key, str) or not key:
            review.problems.append(f"Entry {index} names no sub-task.")
        elif key in answers:
            review.problems.append(f"{key} is planned twice.")
        elif key in review.done:
            review.notes.append(f"{key} is done in Jira; the planner's entry for it was left out.")
        elif key not in review.by_key:
            review.problems.append(f"{key} is not an open sub-task of {review.story.story.key}.")
        else:
            answers[key] = raw
    review.problems += [
        f"{key} has no entry in the planner's answer."
        for key in review.by_key
        if key not in answers
    ]
    return answers


def _jira_dependencies(
    review: _Review, item: WorkItem, given: list[Any], reasons_given: dict[str, Any]
) -> dict[str, str]:
    """Jira's own "is blocked by" links among the open sub-tasks: always kept."""
    reasons: dict[str, str] = {}
    task_id = review.by_key[item.key]["id"]
    for blocker in (key for key in item.blocked_by if key in review.by_key):
        if blocker not in given:
            review.notes.append(
                f"{task_id} ({item.key}) waits for {review.by_key[blocker]['id']} ({blocker}): "
                "a Jira link the planner left out, put back."
            )
        reason = reasons_given.get(blocker)
        reasons[blocker] = (
            reason.strip()
            if isinstance(reason, str) and reason.strip()
            else _jira_reason(item, blocker)
        )
    return reasons


def _dependencies(
    review: _Review, item: WorkItem, given: list[Any], reasons_given: dict[str, Any]
) -> dict[str, str]:
    """Jira's dependencies plus the planner's, each with its reason, by sub-task key."""
    reasons = _jira_dependencies(review, item, given, reasons_given)
    for blocker in given:
        if not isinstance(blocker, str):
            review.problems.append(f"{item.key} has a dependency that is not a sub-task key.")
            continue
        if blocker in reasons:
            continue
        reason = reasons_given.get(blocker)
        if blocker in review.done:
            review.notes.append(
                f"{item.key}: its dependency {blocker} is already done in Jira; left out."
            )
        elif blocker not in review.by_key or blocker == item.key:
            review.problems.append(
                f"{item.key} depends on {blocker}, which is not another open sub-task of "
                f"{review.story.story.key}."
            )
        elif not isinstance(reason, str) or not reason.strip():
            review.problems.append(f"{item.key} depends on {blocker} without a reason.")
        else:
            reasons[blocker] = reason.strip()
            review.jira_links.append(
                {"subtask": item.key, "blocked_by": blocker, "reason": reason.strip()}
            )
    return reasons


def _doc_target(review: _Review, key: str, target: Any, docs_dir: str) -> Any:
    """A doc target must be inside the docs folder; with no docs folder there is none."""
    if target and not docs_dir:
        review.notes.append(
            f"{key}: no docs folder is set (BRIGADE_DOCS_DIR), so its doc_target {target} "
            "was left out."
        )
        return None
    if isinstance(target, str) and target and not _inside(target, docs_dir):
        review.problems.append(f"{key}: doc_target {target} is not in the docs folder {docs_dir}/.")
    return target


def _merge_one(review: _Review, item: WorkItem, raw: dict[str, Any], docs_dir: str) -> dict:
    given = raw.get("depends_on") or []
    reasons_given = raw.get("dependency_reasons") or {}
    if not isinstance(given, list) or not isinstance(reasons_given, dict):
        review.problems.append(
            f"{item.key}: depends_on must be a list and dependency_reasons an object."
        )
        return {}
    by_key = review.by_key
    reasons = _dependencies(review, item, given, reasons_given)
    merged = {**by_key[item.key], **{name: raw[name] for name in PLANNER_FIELDS if name in raw}}
    merged["depends_on"] = [by_key[blocker]["id"] for blocker in reasons]
    merged["dependency_reasons"] = {
        by_key[blocker]["id"]: reason for blocker, reason in reasons.items()
    }
    merged["doc_target"] = _doc_target(review, item.key, merged.get("doc_target"), docs_dir)
    merged.setdefault("context", {"read_first": [], "notes": ""})
    return merged


def merge_planner_output(story: Story, output: dict[str, Any], docs_dir: str) -> dict[str, Any]:
    """Join the planner's choices to Jira's fields; refuse an answer that does not fit.

    Returns ``{"summary", "tasks", "notes", "jira_links"}``. Every problem found is named in
    one PlanValidationError, so the planner can be asked to fix them all at once.
    """
    by_key = {task["jira_key"]: task for task in jira_tasks(story)}
    items = {item.key: item for item in story.open_subtasks()}
    review = _Review(story, by_key, {item.key for item in story.subtasks if item.done})
    raw_tasks = output.get("tasks")
    if not isinstance(raw_tasks, list):
        raise PlanValidationError("The planner's answer has no task list.")
    answers = _answers(review, raw_tasks)
    tasks = [
        _merge_one(review, items[key], answers[key], docs_dir) for key in by_key if key in answers
    ]
    if review.problems:
        raise PlanValidationError(" ".join(review.problems))

    claimed = {task["id"] for task in tasks if task.get("parallel_safe") is True}
    checked = validate_tasks(tasks)
    review.notes += [
        f"{task['id']} ({task['jira_key']}) runs one at a time: it shares files with a task "
        "it is not ordered against, or does not list its files."
        for task in checked
        if task["id"] in claimed and not task["parallel_safe"]
    ]
    summary = output.get("summary")
    return {
        "summary": summary.strip() if isinstance(summary, str) else "",
        "tasks": checked,
        "notes": review.notes,
        "jira_links": review.jira_links,
    }
