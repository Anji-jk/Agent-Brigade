"""The checks of one built attempt: measure its worktree, record the rows. No agent runs.

check_attempt   look at what the Builder left in the attempt worktree (changed files, protected
                paths, files outside the task's Files), run the task's own Verify lines there, and
                write the results to the checks table. Nothing is committed or decided here.
"""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select

from core.db import get_session, init_db
from core.db.models import Attempt, StoryRun, SubTask
from core.db.repositories import attempt_rows
from core.settings import Settings
from pipeline.checks.measure import CheckReport, measure_attempt
from pipeline.stages.builder_run import BuildError
from pipeline.stages.check_report import check_rows
from pipeline.stages.prepare import approved_plan, project_root
from pipeline.workspace import layout


def _task(plan: dict[str, Any], key: str) -> dict[str, Any]:
    for task in plan["tasks"]:
        if task.get("jira_key") == key:
            return task
    raise BuildError(f"{key} is not a task of run {plan.get('run_id')}.")


def check_attempt(
    settings: Settings, run_id: str, key: str, number: int = 1, engine: Engine | None = None
) -> CheckReport:
    """Measure attempt `number` of `key`. BuildError: there is nothing built to check."""
    root = project_root(settings)
    task = _task(approved_plan(root, run_id), key)
    worktree = layout.attempt_worktree(settings.worktrees_dir, run_id, key, number)
    if not Path(worktree).is_dir():
        raise BuildError(f"There is no worktree for attempt {number} of {key}: build it first.")
    engine = init_db(engine)
    with get_session(engine) as session:
        sub = session.scalar(
            select(SubTask).join(StoryRun).where(StoryRun.run_id == run_id, SubTask.key == key)
        )
        attempt = attempt_rows.attempt_of(session, sub, number) if sub else None
        if sub is None or attempt is None:
            raise BuildError(f"Attempt {number} of {key} has no database row: build it first.")
        attempt_id, sub_id = attempt.id, sub.id
    report = measure_attempt(Path(worktree), task, key, number, timeout=settings.test_timeout)
    with get_session(engine) as session:
        sub, attempt = session.get(SubTask, sub_id), session.get(Attempt, attempt_id)
        if sub is None or attempt is None:
            raise BuildError("The attempt's rows vanished from the database.")
        attempt_rows.record_checks(session, attempt, sub, check_rows(report))
    return report
