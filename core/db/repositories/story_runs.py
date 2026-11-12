"""Queries for story_runs: one row per planning run of a story.

A row is made when planning starts, with the run id that names its folder and plan.json. Its
status then moves: planning -> waiting (a plan to review) or failed; waiting -> approved or
superseded (a re-plan replaced it); approved -> superseded (another plan of the story was
approved). The approved row is the story's run: Phase 4 builds from it.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models import StoryRun

PLANNING, WAITING, APPROVED, SUPERSEDED, FAILED = (
    "planning",
    "waiting",
    "approved",
    "superseded",
    "failed",
)
STATUSES = (PLANNING, WAITING, APPROVED, SUPERSEDED, FAILED)


def run_id_taken(session: Session, run_id: str) -> bool:
    return session.scalar(select(StoryRun.id).where(StoryRun.run_id == run_id)) is not None


def start_run(
    session: Session,
    project_id: int,
    story_key: str,
    run_id: str,
    budget: float | None,
    now: datetime,
) -> StoryRun:
    row = StoryRun(
        project_id=project_id,
        story_key=story_key,
        run_id=run_id,
        status=PLANNING,
        budget=budget,
        started_at=now,
    )
    session.add(row)
    session.flush()
    return row


def get_run(session: Session, project_id: int, run_id: str) -> StoryRun | None:
    return session.scalar(
        select(StoryRun).where(StoryRun.project_id == project_id, StoryRun.run_id == run_id)
    )


def _of_story(project_id: int, story_key: str):
    return select(StoryRun).where(
        StoryRun.project_id == project_id, StoryRun.story_key == story_key
    )


def runs_of_story(session: Session, project_id: int, story_key: str) -> list[StoryRun]:
    """Newest first."""
    query = _of_story(project_id, story_key).order_by(
        StoryRun.started_at.desc(), StoryRun.id.desc()
    )
    return list(session.scalars(query))


def runs_with_status(
    session: Session, project_id: int, story_key: str, status: str
) -> list[StoryRun]:
    return list(session.scalars(_of_story(project_id, story_key).where(StoryRun.status == status)))


def latest_runs(session: Session, project_id: int) -> dict[str, StoryRun]:
    """Each story's newest run, by story key."""
    query = (
        select(StoryRun)
        .where(StoryRun.project_id == project_id)
        .order_by(StoryRun.started_at, StoryRun.id)
    )
    return {row.story_key: row for row in session.scalars(query)}


def fail_unfinished(session: Session, reason: str, now: datetime) -> int:
    """Mark every run still planning as failed (Brigade stopped while it planned)."""
    rows = list(session.scalars(select(StoryRun).where(StoryRun.status == PLANNING)))
    for row in rows:
        row.status, row.error, row.ended_at = FAILED, reason, now
    session.flush()
    return len(rows)
