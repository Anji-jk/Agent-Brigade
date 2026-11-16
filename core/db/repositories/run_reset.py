"""Forget what the builds of one run wrote, so that the run can be built again from nothing.

The story loop trusts these rows: a task whose newest attempt is Done is merged from its saved
commit, with no agent. That is right for resuming, and wrong after the run's branches were thrown
away to start over, so a restart must remove them. The run's own row stays, with its status, and
so do the Jira items and every other run.
"""

from typing import cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from core.db.models import (
    AgentRun,
    Attempt,
    BudgetReservation,
    Check,
    Merge,
    StoryRun,
    SubTask,
)


def reset_run(session: Session, run_id: str) -> dict[str, int]:
    """Delete the sub-task, attempt, agent, check, merge and budget rows of `run_id`.

    Returns how many of each were removed ({} when the database does not know the run).
    The rows go children first: the tables have no cascade rules.
    """
    story = session.scalar(select(StoryRun).where(StoryRun.run_id == run_id))
    if story is None:
        return {}
    subs = select(SubTask.id).where(SubTask.story_run_id == story.id)
    attempts = select(Attempt.id).where(Attempt.sub_task_id.in_(subs))
    agents = select(AgentRun.id).where(AgentRun.attempt_id.in_(attempts))
    removed = {}
    for name, model, where in (
        ("budget_reservations", BudgetReservation, BudgetReservation.story_run_id == story.id),
        ("merges", Merge, Merge.attempt_id.in_(attempts)),
        ("checks", Check, Check.attempt_id.in_(attempts)),
        ("agent_runs", AgentRun, AgentRun.id.in_(agents)),
        ("attempts", Attempt, Attempt.id.in_(attempts)),
        ("sub_tasks", SubTask, SubTask.id.in_(subs)),
    ):
        deleted = cast(CursorResult, session.execute(delete(model).where(where)))
        removed[name] = deleted.rowcount
    order = ("sub_tasks", "attempts", "agent_runs", "checks", "merges", "budget_reservations")
    return {name: removed[name] for name in order}
