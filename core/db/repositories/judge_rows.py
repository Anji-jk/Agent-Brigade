"""Queries for what judging an attempt writes: its outcome, its reason and its commit.

The Tester and the Reviewer are agent_runs rows like the Builder (attempt_rows.start_agent_run
and finish_agent_run take the role). This module finds the rows of one attempt and closes the
attempt with the decision. A sub-task is done when its attempt is; any other outcome leaves it
in error until a later attempt starts (attempt_rows.start_attempt sets it running again).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models import Attempt, StoryRun, SubTask
from core.db.repositories import attempt_rows

STAGE = "decision"


def rows_of_attempt(
    session: Session, run_id: str, key: str, number: int
) -> tuple[SubTask, Attempt]:
    """The sub_tasks and attempts rows of attempt `number` of `key`, or BuildRecordError."""
    sub = session.scalar(
        select(SubTask).join(StoryRun).where(StoryRun.run_id == run_id, SubTask.key == key)
    )
    attempt = attempt_rows.attempt_of(session, sub, number) if sub else None
    if sub is None or attempt is None:
        raise attempt_rows.BuildRecordError(
            f"Attempt {number} of {key} has no database row: build it first."
        )
    return sub, attempt


def set_stage(session: Session, sub_task: SubTask, stage: str) -> None:
    sub_task.current_stage = stage
    session.flush()


def record_outcome(
    session: Session, attempt: Attempt, sub_task: SubTask, *, outcome: str, reason: str,
    commit_sha: str | None, now: datetime,
) -> None:  # fmt: skip
    """Close the attempt with the decision (done, failed or needs_review) and its commit."""
    attempt.commit_sha = commit_sha
    attempt_rows.finish_attempt(
        session, attempt, sub_task, outcome=outcome, reason=reason, stage=STAGE,
        status=attempt_rows.DONE if outcome == "done" else attempt_rows.ERROR, now=now,
    )  # fmt: skip
