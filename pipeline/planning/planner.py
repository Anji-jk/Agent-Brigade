"""Plan one Jira story with the read-only Planner agent and save the checked plan.

    readiness checks -> Planner (Read, Grep, Glob in the project) -> 3.3's checks -> plan.json

The conversation with the agent (limits, permissions, the fix round, the Git guard) is in
planner_session.py. A plan may carry a budget for the whole story (planning and building), and a
re-plan (replan.py) passes the previous plan and the changes a person asked for. No Jira,
database or Git write happens here: the branch agent/<run_id> is only named.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.runs import new_run_id, run_directory, validate_run_id
from core.settings import Settings
from core.trackers.models import Story
from pipeline.planning.plan_fields import PlanValidationError
from pipeline.planning.plan_file import load_plan, plan_path, save_plan
from pipeline.planning.planner_limits import planner_limits
from pipeline.planning.planner_prompt import MAX_FILES_CHARS, planner_prompt
from pipeline.planning.planner_session import (
    AGENT,
    REPO_ROOT,
    PlanningError,
    ask_planner,
)
from pipeline.planning.readiness import StoryCheck, run_checks
from pipeline.planning.story_plan import WAITING
from pipeline.planning.story_tasks import jira_tasks
from pipeline.runner.claude_runner import AgentRunner, agent_header
from pipeline.workspace.git import (
    GitError,
    commit_of,
    repository_root,
    tracked_files,
    validate_base_ref,
)

__all__ = ["REPO_ROOT", "NotReady", "PlanResult", "PlanningError", "plan_story"]


class NotReady(PlanningError):
    """A readiness check failed, so the Planner was not started."""

    def __init__(self, checks: StoryCheck) -> None:
        super().__init__(f"{len(checks.failed)} readiness check(s) failed.")
        self.checks = checks


@dataclass(frozen=True)
class PlanResult:
    run_id: str
    path: Path
    record: dict[str, Any]
    checks: StoryCheck


def docs_folder(root: Path, configured: str) -> str:
    """The docs folder the plan may point at: the configured one, if the project has it."""
    return configured if configured and (root / configured).is_dir() else ""


def check_budget(budget: float | None) -> float | None:
    """The story budget in dollars, or None when none was set."""
    if budget is None:
        return None
    if isinstance(budget, bool) or not isinstance(budget, (int, float)):
        raise PlanningError("The budget must be a number of dollars.")
    if not math.isfinite(budget) or budget <= 0:
        raise PlanningError("The budget must be more than $0.")
    return float(budget)


def plan_record(story: Story, checked: dict, config: dict, metrics: dict) -> dict[str, Any]:
    """plan.json's content, in Agent Lab's schema_version 2 shape."""
    item, epic = story.story, story.epic
    return {
        "source": {
            "kind": "jira",
            "key": item.key,
            "url": item.url,
            "epic": {"key": epic.key, "summary": epic.summary} if epic else None,
        },
        "issue": {"key": item.key, "title": item.summary, "url": item.url},
        "config": config,
        "summary": checked["summary"],
        "tasks": checked["tasks"],
        "skipped_subtasks": [{"key": s.key, "status": s.status} for s in story.subtasks if s.done],
        "orchestrator_notes": checked["notes"],
        "approval": {"status": WAITING, "jira_links": checked["jira_links"]},
        "planner": metrics,
    }


def plan_story(
    story: Story,
    settings: Settings,
    runner: AgentRunner,
    *,
    run_tests: bool = True,
    run_id: str | None = None,
    budget: float | None = None,
    previous: dict[str, Any] | None = None,
    changes: str | None = None,
) -> PlanResult:
    """Check, plan and save one story. PlanningError (or NotReady) says why it stopped.

    `budget` is the most the whole story may spend, planning and building together; it is
    written into the plan and lowers this run's own spending limit if it is smaller.
    `previous` and `changes` make this a re-plan; replan.py is the way to ask for one.
    """
    budget = check_budget(budget)
    try:
        jira_tasks(story)
    except PlanValidationError as exc:
        raise PlanningError(str(exc)) from None
    checks = run_checks(story, settings, run_tests=run_tests)
    if not checks.ready:
        raise NotReady(checks)
    try:
        if settings.project_path is None:
            raise PlanningError("A project folder must be configured before planning.")
        root = repository_root(settings.project_path)
        base = validate_base_ref(settings.base_branch)
        run_id = (
            validate_run_id(run_id)
            if run_id
            else new_run_id(
                story.story.key, lambda candidate: run_directory(root, candidate).exists()
            )
        )
        if plan_path(root, run_id).exists():
            raise PlanningError(f"A plan already exists for run {run_id}.")
        docs = docs_folder(root, settings.docs_dir)
        prompt = planner_prompt(
            story,
            project_root=root,
            base_branch=base,
            docs_dir=docs,
            files=tracked_files(root, MAX_FILES_CHARS),
            budget=budget,
            previous=previous,
            changes=changes,
        )
        money = planner_limits().money_for(budget)
        checked, metrics = ask_planner(story, runner, root, prompt, docs, money)
        config = {
            "base_ref": base,
            "base_commit": commit_of(root, base),
            "model": agent_header(REPO_ROOT, AGENT).get("model"),
            "timeout_seconds": planner_limits().timeout_seconds,
            "run_id": run_id,
            "branch": f"agent/{run_id}",
            "worktree_path": None,
            "docs_dir": docs or None,
            "budget_usd": budget,
            "replan": (
                {"from_run": previous["run_id"], "changes": (changes or "").strip()}
                if previous
                else None
            ),
        }
        save_plan(root, run_id, plan_record(story, checked, config, metrics))
    except GitError as exc:
        raise PlanningError(str(exc)) from None
    return PlanResult(run_id, plan_path(root, run_id), load_plan(root, run_id), checks)
