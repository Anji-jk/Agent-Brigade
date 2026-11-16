"""What every stage after the Builder starts from: the task, the worktree, the earlier reports.

The stages are separate commands (check, test, judge), each of which can be run alone, so they
hand work to each other through the reports in ``<project>/.agent-brigade/runs/<run_id>/``:
``build/``, ``checks/``, ``test/`` and ``judge/``, one ``<KEY>-<n>.json`` each. A stage that
finds the report it needs missing says which command makes it.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.runs import run_directory
from core.settings import Settings
from pipeline.stages.errors import BuildError
from pipeline.stages.prepare import approved_plan, project_root
from pipeline.workspace import layout


def read_report(path: Path) -> dict[str, Any] | None:
    """A stage's report, or None when it is missing or not readable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def report_path(root: Path, run_id: str, stage: str, key: str, number: int) -> Path:
    return run_directory(root, run_id) / stage / f"{key}-{number}.json"


@dataclass
class Inputs:
    run_id: str
    key: str
    number: int
    root: Path
    plan: dict[str, Any]
    task: dict[str, Any]
    worktree: Path
    check: dict[str, Any] | None  # checks/<KEY>-<n>.json
    build: dict[str, Any] | None  # build/<KEY>-<n>.json
    test: dict[str, Any] | None  # test/<KEY>-<n>.json

    @property
    def criteria(self) -> list[str]:
        return list(self.task["acceptance_criteria"])


def find_task(plan: dict[str, Any], key: str) -> dict[str, Any]:
    for task in plan["tasks"]:
        if task.get("jira_key") == key:
            return task
    raise BuildError(f"{key} is not a task of run {plan.get('run_id')}.")


def load_inputs(settings: Settings, run_id: str, key: str, number: int) -> Inputs:
    """The plan's task, the attempt worktree and the reports so far. BuildError: no worktree."""
    root = project_root(settings)
    plan = approved_plan(root, run_id)
    task = find_task(plan, key)
    worktree = layout.attempt_worktree(settings.worktrees_dir, run_id, key, number)
    if not Path(worktree).is_dir():
        raise BuildError(f"There is no worktree for attempt {number} of {key}: build it first.")
    read = {
        stage: read_report(report_path(root, run_id, stage, key, number))
        for stage in ("checks", "build", "test")
    }
    return Inputs(
        run_id, key, number, root, plan, task, Path(worktree),
        read["checks"], read["build"], read["test"],
    )  # fmt: skip
