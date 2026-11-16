"""Queries for what merging writes: the merges table, and a failed merge on its attempt.

A merge turns a Done attempt into part of the story branch. If it cannot (a conflict, or a check
that fails on the combined code) the attempt becomes Failed with the reason, and the sub-task
goes back to error until a later attempt starts. The story branch itself is not in the database:
whether a commit is merged is answered by Git.
"""

from datetime import datetime
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models import Attempt, Merge, StoryRun, SubTask
from core.db.repositories import attempt_rows

STAGE = "merge"
REASON_CHARS = 1000


class AttemptFact(NamedTuple):
    key: str
    number: int
    outcome: str | None
    commit_sha: str | None


def attempts_of_run(session: Session, run_id: str) -> list[AttemptFact]:
    """Every attempt of the run, oldest first (the newest of a task is the last it has)."""
    rows = session.execute(
        select(SubTask.key, Attempt.number, Attempt.outcome, Attempt.commit_sha)
        .join(Attempt, Attempt.sub_task_id == SubTask.id)
        .join(StoryRun, StoryRun.id == SubTask.story_run_id)
        .where(StoryRun.run_id == run_id)
        .order_by(Attempt.id)
    )
    return [AttemptFact(*row) for row in rows]


def newest_attempt(session: Session, run_id: str, key: str) -> tuple[SubTask, Attempt] | None:
    """The sub_tasks row of `key` and its newest attempt, or None when it has none."""
    sub = session.scalar(
        select(SubTask).join(StoryRun).where(StoryRun.run_id == run_id, SubTask.key == key)
    )
    if sub is None:
        return None
    attempt = session.scalar(
        select(Attempt).where(Attempt.sub_task_id == sub.id).order_by(Attempt.id.desc())
    )
    return (sub, attempt) if attempt is not None else None


def record_merge(
    session: Session, attempt: Attempt, sub_task: SubTask, *, kind: str, commit: str,
    tests_passed: bool | None, now: datetime,
) -> None:  # fmt: skip
    """A merge row (kind: fast-forward | real) and the sub-task's stage."""
    session.add(
        Merge(
            attempt_id=attempt.id, kind=kind, commit=commit, tests_passed=tests_passed,
            merged_at=now,
        )
    )  # fmt: skip
    sub_task.current_stage = "merged"
    session.flush()


def fail_merge(
    session: Session, attempt: Attempt, sub_task: SubTask, *, reason: str, now: datetime
) -> None:
    """The attempt could not be merged: Failed, with why. The commit it made stays recorded."""
    attempt_rows.finish_attempt(
        session, attempt, sub_task, outcome="failed", reason=reason[:REASON_CHARS], stage=STAGE,
        status=attempt_rows.ERROR, now=now,
    )  # fmt: skip


def merges_of(session: Session, attempt_id: int) -> list[Merge]:
    return list(session.scalars(select(Merge).where(Merge.attempt_id == attempt_id)))
