"""The database rows a run's builds wrote, as text: sub_tasks, attempts and agent_runs."""

from sqlalchemy import Engine, select

from core.db import get_session, init_db
from core.db.models import AgentRun, Attempt, StoryRun, SubTask


def format_rows(engine: Engine, run_id: str) -> str:
    """One line per row, sub-tasks first, each with its attempts and their agent runs."""
    engine = init_db(engine)
    lines: list[str] = []
    with get_session(engine) as session:
        story = session.scalar(select(StoryRun).where(StoryRun.run_id == run_id))
        if story is None:
            return f"Run {run_id} is not in the database."
        lines.append(f"story_runs  {story.run_id}  status={story.status}")
        sub_tasks = session.scalars(select(SubTask).where(SubTask.story_run_id == story.id))
        for sub in sub_tasks:
            lines.append(
                f"sub_tasks   #{sub.id} {sub.key}  status={sub.status} stage={sub.current_stage} "
                f"size={sub.size} depends_on={sub.depends_on}"
            )
            for attempt in session.scalars(select(Attempt).where(Attempt.sub_task_id == sub.id)):
                lines.append(
                    f"  attempts    #{attempt.id} number={attempt.number} "
                    f"outcome={attempt.outcome} reason={attempt.reason} branch={attempt.branch}"
                )
                for run in session.scalars(
                    select(AgentRun).where(AgentRun.attempt_id == attempt.id)
                ):
                    lines.append(
                        f"    agent_runs  #{run.id} {run.role} status={run.status} "
                        f"model={run.model_used or run.model_requested} effort={run.effort} "
                        f"turns={run.turns} cost={run.cost} seconds={run.duration_s} "
                        f"tokens={run.input_tokens}/{run.output_tokens}/{run.cache_tokens} "
                        f"session={run.session_id} exit={run.exit_reason}"
                    )
    return "\n".join(lines)
