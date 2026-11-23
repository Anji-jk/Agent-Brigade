"""Open the attempt of a documentation task: its worktree, branch and database rows.

A documentation task has no Builder, but it is still an attempt: a worktree from the story tip
(with the setup lines run, so that its check lines can run), a branch, and rows. This does what
the Builder's first half does and nothing else. A continued attempt uses what is already there.
"""

from dataclasses import dataclass

from sqlalchemy import Engine

from core.settings import Settings
from pipeline.stages.attempt_log import AttemptLog
from pipeline.stages.attempt_resume import reopen_rows, resume_ready
from pipeline.stages.builder_run import _start_rows, _sub_task_id
from pipeline.stages.errors import BuildError
from pipeline.stages.prepare import approved_plan, prepare_attempt, project_root
from pipeline.stages.prepare_report import AttemptReady
from pipeline.stages.schedule import start_blockers
from pipeline.stages.stage_inputs import find_task


@dataclass
class OpenAttempt:
    ready: AttemptReady
    attempt_id: int
    sub_task_id: int


def open_attempt(
    settings: Settings, run_id: str, key: str, number: int, engine: Engine, *,
    resume: bool = False, stage: str = "builder",
) -> OpenAttempt:  # fmt: skip
    """BuildError: the task cannot start yet, or its attempt cannot be continued."""
    root = project_root(settings)
    plan = approved_plan(root, run_id)
    task = find_task(plan, key)
    sub_task_id = _sub_task_id(engine, settings, plan, task, run_id)
    log = AttemptLog(root, run_id, key, number)
    if resume:
        ready = resume_ready(settings, run_id, key, number)
        attempt_id = reopen_rows(engine, run_id, key, number, stage)
        log.emit("worktree_reused", branch=ready.branch)
        return OpenAttempt(ready, attempt_id, sub_task_id)
    blockers = start_blockers(root, plan, run_id, key, engine)
    if blockers:
        raise BuildError(f"{key} cannot start yet:\n" + "\n".join(f"- {text}" for text in blockers))
    ready = prepare_attempt(settings, run_id, key, number)
    log.emit("worktree_ready", branch=ready.branch, setup_ok=ready.ok)
    return OpenAttempt(ready, _start_rows(engine, sub_task_id, number, ready), sub_task_id)
