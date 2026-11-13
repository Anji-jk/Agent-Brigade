"""Prepare the ground for a build, from an approved plan. No agent runs and nothing is spent.

prepare_story   the story branch at the plan's base commit, the story worktree, the plan's setup
                lines, then the project's own checks once on the untouched branch (the baseline)
prepare_attempt a fresh worktree for one attempt of one sub-task, from the story branch tip, with
                the setup lines run in it
clean_run       remove the run's worktrees; branches stay

The project's folder, checked-out branch and files are never touched. The commands are the
plan's approved lines and nothing else.
"""

from pathlib import Path
from typing import Any

from core.settings import Settings
from pipeline.planning.plan_file import load_plan
from pipeline.planning.story_plan import APPROVED
from pipeline.stages.prepare_report import (
    AttemptReady,
    Prepared,
    StepResult,
    step_result,
    write_report,
)
from pipeline.workspace import layout, worktrees
from pipeline.workspace.commands import run_command
from pipeline.workspace.git import GitError, changed_files, commit_of, repository_root


class PrepareError(RuntimeError):
    """Preparing was refused or stopped. The message says why and what is left behind."""


def project_root(settings: Settings) -> Path:
    if settings.project_path is None:
        raise PrepareError("BRIGADE_PROJECT_PATH is empty in .env.")
    return repository_root(settings.project_path)


def approved_plan(root: Path, run_id: str) -> dict[str, Any]:
    plan = load_plan(root, run_id)
    status = (plan.get("approval") or {}).get("status")
    if status != APPROVED:
        raise PrepareError(
            f"Run {run_id} is {status or 'not approved'}: approve its plan before building."
        )
    return plan


def _run_lines(
    lines: list[str], worktree: Path, timeout: int, *, stop_on_failure: bool
) -> list[StepResult]:
    results: list[StepResult] = []
    for line in lines:
        results.append(step_result(run_command(line, worktree, timeout=timeout)))
        if stop_on_failure and results[-1].status == "failed":
            break
    return results


def prepare_story(settings: Settings, run_id: str) -> tuple[Prepared, Path]:
    """Branch, story worktree, setup, baseline. Returns what happened and the report path."""
    root = project_root(settings)
    plan = approved_plan(root, run_id)
    branch, base = layout.story_branch(run_id), plan["config"]["base_commit"]
    if plan["config"]["branch"] != branch:
        raise PrepareError(f"The plan names the branch {plan['config']['branch']!r}, not {branch}.")
    if commit_of(root, base) is None:
        raise PrepareError(f"The plan's base commit {base[:12]} is not in the project any more.")
    path = layout.story_worktree(settings.worktrees_dir, run_id)
    try:
        worktrees.create_branch(root, branch, base)
        worktrees.add_story_worktree(root, path, branch)
    except GitError as exc:
        raise PrepareError(
            f"{exc} A run is prepared once: python -m pipeline.stages clean {run_id} "
            "removes its worktrees (branches stay)."
        ) from None
    prepared = Prepared(run_id, branch, base, str(path))
    commands = plan["commands"]
    timeout = settings.test_timeout
    prepared.setup = _run_lines(commands["setup"], path, timeout, stop_on_failure=True)
    if prepared.ok:
        prepared.baseline = _run_lines(
            commands["project_checks"], path, timeout, stop_on_failure=False
        )
    prepared.leftovers = changed_files(path)[:20]
    return prepared, write_report(root, prepared)


def prepare_attempt(settings: Settings, run_id: str, key: str, number: int = 1) -> AttemptReady:
    """A fresh worktree for attempt `number` of sub-task `key`, with the setup lines run."""
    root = project_root(settings)
    plan = approved_plan(root, run_id)
    if key not in {task.get("jira_key") for task in plan["tasks"]}:
        raise PrepareError(f"{key} is not a task of run {run_id}.")
    story = layout.story_branch(run_id)
    start = commit_of(root, f"refs/heads/{story}")
    if start is None:
        raise PrepareError(f"Run {run_id} has no story branch yet: prepare the run first.")
    branch = layout.attempt_branch(run_id, key, number)
    path = layout.attempt_worktree(settings.worktrees_dir, run_id, key, number)
    try:
        worktrees.add_attempt_worktree(root, path, branch, start)
    except GitError as exc:
        raise PrepareError(str(exc)) from None
    ready = AttemptReady(run_id, key, number, branch, start, str(path))
    ready.setup = _run_lines(
        plan["commands"]["setup"], path, settings.test_timeout, stop_on_failure=True
    )
    return ready


def clean_run(settings: Settings, run_id: str, *, discard_changes: bool = False) -> list[str]:
    """Remove the run's worktrees, attempts first. Branches are kept. Returns what happened."""
    root = project_root(settings)
    folder = layout.run_worktrees(settings.worktrees_dir, run_id).resolve()
    mine = [
        info for info in worktrees.list_worktrees(root)[1:] if folder in info.path.resolve().parents
    ]
    mine.sort(key=lambda info: info.path.name == "story")  # attempts first, the story last
    report: list[str] = []
    for info in mine:
        try:
            worktrees.remove_worktree(root, info.path, discard_changes=discard_changes)
            report.append(f"removed {info.path}")
        except GitError as exc:
            report.append(f"kept {info.path}: {exc}")
    if not report:
        report.append(f"no worktrees of run {run_id} were found.")
    return report
