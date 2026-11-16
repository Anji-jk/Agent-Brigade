"""What a run has written so far, task by task: attempts, their agents and merge. Read only."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models import AgentRun, Attempt, Merge, SubTask


@dataclass(frozen=True)
class AttemptRows:
    attempt: Attempt
    agents: list[AgentRun]
    merge: Merge | None


@dataclass(frozen=True)
class TaskRows:
    sub_task: SubTask
    attempts: list[AttemptRows]


def rows_of_run(session: Session, story_run_id: int) -> list[TaskRows]:
    """Every sub-task of the run (oldest first) with its attempts, agent runs and merge."""
    subs = list(
        session.scalars(
            select(SubTask).where(SubTask.story_run_id == story_run_id).order_by(SubTask.id)
        )
    )
    attempts = list(
        session.scalars(
            select(Attempt)
            .where(Attempt.sub_task_id.in_([sub.id for sub in subs]))
            .order_by(Attempt.number, Attempt.id)
        )
    )
    ids = [attempt.id for attempt in attempts]
    agents = session.scalars(
        select(AgentRun).where(AgentRun.attempt_id.in_(ids)).order_by(AgentRun.id)
    )
    merges = session.scalars(select(Merge).where(Merge.attempt_id.in_(ids)).order_by(Merge.id))
    agents_of: dict[int, list[AgentRun]] = {}
    for agent in agents:
        agents_of.setdefault(agent.attempt_id, []).append(agent)
    merge_of = {merge.attempt_id: merge for merge in merges}  # the newest one wins
    return [
        TaskRows(
            sub,
            [
                AttemptRows(a, agents_of.get(a.id, []), merge_of.get(a.id))
                for a in attempts
                if a.sub_task_id == sub.id
            ],
        )
        for sub in subs
    ]