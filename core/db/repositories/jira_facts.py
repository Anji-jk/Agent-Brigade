"""What the Jira comments quote from the database: the money spent on each sub-task of a run."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db.models import AgentRun, Attempt, StoryRun, SubTask


def cost_by_task(session: Session, run_id: str) -> dict[str, float]:
    """Every attempt's agents added up per sub-task key (a task nothing was spent on is absent)."""
    rows = session.execute(
        select(SubTask.key, func.sum(AgentRun.cost))
        .join(StoryRun, SubTask.story_run_id == StoryRun.id)
        .join(Attempt, Attempt.sub_task_id == SubTask.id)
        .join(AgentRun, AgentRun.attempt_id == Attempt.id)
        .where(StoryRun.run_id == run_id)
        .group_by(SubTask.key)
    )
    return {key: float(total or 0) for key, total in rows}
