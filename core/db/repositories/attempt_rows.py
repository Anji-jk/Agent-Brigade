"""Queries for sub_tasks, attempts and agent_runs: what building a story writes.

A sub_tasks row is made the first time a sub-task is built in a run; each try at it is an
attempts row, and each Claude Code session of that try is an agent_runs row with its usage.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models import AgentRun, Attempt, SubTask, TrackerItem

QUEUED, RUNNING, DONE, ERROR = "queued", "running", "done", "error"


class BuildRecordError(RuntimeError):
    """The database cannot take the record; the message says what to do."""


def sub_task_row(
    session: Session, story_run_id: int, key: str, size: str | None, depends_on: list[str]
) -> SubTask:
    """The run's row for this sub-task, made if it does not exist."""
    row = session.scalar(
        select(SubTask).where(SubTask.story_run_id == story_run_id, SubTask.key == key)
    )
    if row is not None:
        return row
    if session.get(TrackerItem, key) is None:
        raise BuildRecordError(f"{key} is not on the synced board: press Sync, then try again.")
    row = SubTask(
        story_run_id=story_run_id,
        key=key,
        status=QUEUED,
        depends_on=",".join(depends_on) or None,
        size=size,
    )
    session.add(row)
    session.flush()
    return row


def start_attempt(
    session: Session, sub_task: SubTask, number: int, branch: str, worktree: str, now: datetime
) -> Attempt:
    attempt = Attempt(
        sub_task_id=sub_task.id,
        number=number,
        branch=branch,
        working_copy=worktree,
        started_at=now,
    )
    sub_task.status, sub_task.current_stage = RUNNING, "builder"
    session.add(attempt)
    session.flush()
    return attempt


def finish_attempt(
    session: Session, attempt: Attempt, sub_task: SubTask, *, outcome: str, reason: str | None,
    stage: str, status: str, now: datetime,
) -> None:  # fmt: skip
    attempt.outcome, attempt.reason, attempt.ended_at = outcome, reason, now
    sub_task.status, sub_task.current_stage = status, stage
    session.flush()


def start_agent_run(
    session: Session, attempt: Attempt, role: str, model: str, effort: str, session_id: str,
    now: datetime,
) -> AgentRun:  # fmt: skip
    row = AgentRun(
        attempt_id=attempt.id,
        role=role,
        model_requested=model,
        effort=effort,
        session_id=session_id,
        status=RUNNING,
        started_at=now,
    )
    session.add(row)
    session.flush()
    return row


def finish_agent_run(
    session: Session, row: AgentRun, reply, *, error: str | None, now: datetime
) -> None:
    """Close the row. `reply` is the AgentReply, or None when the agent did not answer."""
    row.ended_at, row.status = now, ERROR if error else DONE
    row.exit_reason = error
    if reply is not None:
        row.model_used, row.turns, row.cost = reply.model_used, reply.turns, reply.cost_usd
        row.input_tokens, row.output_tokens = reply.input_tokens, reply.output_tokens
        row.cache_tokens = reply.cache_tokens
        row.session_id = reply.session_id or row.session_id
        if reply.duration_ms is not None:
            row.duration_s = round(reply.duration_ms / 1000)
    session.flush()


def agent_runs_of(session: Session, attempt_id: int) -> list[AgentRun]:
    return list(
        session.scalars(
            select(AgentRun).where(AgentRun.attempt_id == attempt_id).order_by(AgentRun.id)
        )
    )
