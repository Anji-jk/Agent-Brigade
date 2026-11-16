"""May a sub-task start now? Two rules, answered from Git and the plan, with no agent and no cost.

DEPENDENCIES  every task in its depends_on is merged into the story branch (a commit one of its
              attempts made is part of the story branch's history). The new worktree then starts
              from a tip that holds that work.
OVERLAP       no other task that may touch the same files (planning's overlapping_tasks) is
              running or Done but not merged yet. Two such tasks run one after the other, so a
              merge conflict cannot happen between them and no attempt is wasted on one.

"Running" is the task's newest attempt: not yet judged, Stopped by a person (it will continue, so
it still holds its files), or Done and not merged. An attempt that Failed, needs a person or was
Cancelled is not running; a new attempt replaces it.
"""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories import merge_rows
from pipeline.planning.plan_order import overlapping_tasks
from pipeline.stages.stage_inputs import find_task
from pipeline.workspace import layout
from pipeline.workspace.git import commit_of
from pipeline.workspace.merge import is_ancestor

MERGED, RUNNING, OTHER = "merged", "running", "other"


def task_states(root: Path, run_id: str, engine: Engine) -> dict[str, str]:
    """Each task key with an attempt: merged, running (see above) or other."""
    story = layout.story_branch(run_id)
    with get_session(engine) as session:
        facts = merge_rows.attempts_of_run(session, run_id)
    merged = {
        fact.key
        for fact in facts
        if fact.commit_sha and is_ancestor(root, fact.commit_sha, f"refs/heads/{story}")
    }
    newest = {fact.key: fact for fact in facts}  # oldest first, so the last one wins
    states: dict[str, str] = {}
    for key, fact in newest.items():
        if key in merged:
            states[key] = MERGED
        elif fact.outcome in (None, "built", "stopped") or (
            fact.outcome == "done" and fact.commit_sha
        ):
            states[key] = RUNNING
        else:
            states[key] = OTHER
    return states


def _name(task: dict[str, Any]) -> str:
    return task.get("jira_key") or task["id"]


def start_blockers(
    root: Path, plan: dict[str, Any], run_id: str, key: str, engine: Engine
) -> list[str]:
    """Why `key` cannot start now, one sentence each. Empty: it may start."""
    if commit_of(root, f"refs/heads/{layout.story_branch(run_id)}") is None:
        return []  # nothing to wait for; the worktree step says the run must be prepared first
    task = find_task(plan, key)
    by_id = {t["id"]: t for t in plan["tasks"]}
    states = task_states(root, run_id, engine)
    reasons = []
    for dependency in task["depends_on"]:
        name = _name(by_id[dependency])
        if states.get(name) != MERGED:
            reasons.append(
                f"{name} is not merged into the story branch yet, and {key} depends on it: "
                f"finish {name}, then run merge for it."
            )
    for other_id, shared in overlapping_tasks(plan["tasks"], task["id"]).items():
        name = _name(by_id[other_id])
        if states.get(name) == RUNNING:
            why = (
                f"both change {', '.join(shared[:3])}"
                if shared
                else "one of them names no files, so overlap cannot be ruled out"
            )
            reasons.append(
                f"{name} is running or not merged yet and {why}: wait until it is merged."
            )
    return reasons