"""A person's Stop or Cancel, seen from inside a task that is running.

The page leaves a request (pipeline.control.task_control). An agent that is running notices it
and is killed by its own loop (pipeline.runner.stop_watch). Between stages this module looks
for it too, so a request that arrived while checks ran, or while the worktree was being made,
is not lost. ``guard`` is called before each stage and after each stage that was cut short:

* Stop    the task is *stopped*: it can be continued from the stage it had reached.
* Cancel  the task is *cancelled*: final. Its worktree and branch are kept, never deleted.
* A Stop that arrives after the Judge has finished the attempt well is ignored: it has finished
  already, and it is merged. A Cancel still wins, because nothing is merged yet.

Raising TaskInterrupted ends the task's work in the loop; the settled state is already on disk
and on the attempt's row by then.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories import attempt_rows, merge_rows
from core.runs import run_directory
from pipeline.control import task_control as control
from pipeline.runner.claude_runner import AgentReply, AgentRequest, AgentRunner
from pipeline.stages import checkpoint
from pipeline.stages.attempt_log import AttemptLog

OPEN_OUTCOMES = (None, "built", "error", "stopped")  # a Cancel may overwrite these when idle


class TaskInterrupted(Exception):
    def __init__(self, state: str, stage: str, number: int | None) -> None:
        super().__init__(f"The task was {state}; it resumes from {stage}.")
        self.state, self.stage, self.number = state, stage, number


class StopAware:
    """Hands every request of a task the file whose appearance stops its agent."""

    def __init__(
        self, runner: AgentRunner, stop_file: Path, record_file: Path | None = None
    ) -> None:
        self._runner, self._stop_file, self._record_file = runner, stop_file, record_file

    def run(self, request: AgentRequest) -> AgentReply:
        return self._runner.run(
            replace(request, stop_file=self._stop_file, record_file=self._record_file)
        )


def stop_file_of(root: Path, run_id: str, key: str) -> Path:
    return control.request_path(run_directory(root, run_id), key)


def agent_file_of(root: Path, run_id: str, key: str) -> Path:
    return control.agent_record_path(run_directory(root, run_id), key)


def settle_task(
    engine: Engine, root: Path, run_id: str, key: str, state: str, stage: str,
    number: int | None = None, *, force: bool = False,
) -> None:  # fmt: skip
    """Record the final word: the control file, and the newest attempt's row when it is open.

    `force`: the attempt was in flight, so its row is rewritten whatever it says now (an agent
    that was killed leaves an error behind). Without it only an open row is touched, so a Cancel
    of a task that already Failed does not rewrite what the judge decided.
    """
    control.settle(run_directory(root, run_id), key, state, stage, number)
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, run_id, key)
        if found is None:
            return
        sub, attempt = found
        if number is not None and attempt.number != number:
            return
        if not force and attempt.outcome not in OPEN_OUTCOMES:
            return
        reason = (
            f"{'Stopped' if state == control.STOPPED else 'Cancelled'} by request; "
            f"{'it resumes from' if state == control.STOPPED else 'it was at'} {stage}."
        )
        attempt_rows.finish_attempt(
            session, attempt, sub, outcome=state, reason=reason, stage=stage, status=state,
            now=datetime.now(UTC),
        )  # fmt: skip


def guard(
    engine: Engine, root: Path, run_id: str, key: str, number: int, resume_at: str,
    *, finished: bool = False,
) -> None:  # fmt: skip
    """Raise TaskInterrupted when a person asked to stop or cancel. `resume_at`: the stage the
    task would continue from. `finished`: the attempt was judged Done, so a Stop is too late."""
    run_dir = run_directory(root, run_id)
    action = control.pending(run_dir, key)
    if action is None:
        return
    if action == control.STOP and finished:
        control.clear_request(run_dir, key)
        return
    state = control.STOPPED if action == control.STOP else control.CANCELLED
    settle_task(engine, root, run_id, key, state, resume_at, number, force=True)
    AttemptLog(root, run_id, key, number).emit(f"task_{state}", stage=resume_at)
    raise TaskInterrupted(state, resume_at, number)


def settle_waiting(
    engine: Engine, root: Path, run_id: str, key: str, action: str
) -> tuple[str, str]:
    """Settle a task that no thread is working on (waiting, stopped, or its loop is gone).

    Nothing is running, so nothing needs killing: the word is written at once. Where it would
    resume is the first stage its newest attempt has not finished (builder when it has none).
    Returns (the state, the stage)."""
    state = control.STOPPED if action == control.STOP else control.CANCELLED
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, run_id, key)
    number = found[1].number if found else None
    stage = checkpoint.resume_stage(root, run_id, key, number) if number else "builder"
    settle_task(engine, root, run_id, key, state, stage, number)
    return state, stage
