"""The sums behind the Orchestrator's Overview tab: what all the runs of a project add up to.

Read only, and every number is added up by the database (GROUP BY), never by looping over rows,
so it stays quick with hundreds of runs. A build run is a story_runs row that has sub_tasks; a
plan nobody built is not one, but its planning cost still counts (see planning_totals).
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db.models import AgentRun, Attempt, Merge, StoryRun, SubTask, TrackerItem


@dataclass
class RunUsage:
    """What one build run did so far."""

    statuses: dict[str, int] = field(default_factory=dict)  # sub-task status -> how many
    attempts: int = 0
    tasks_tried: int = 0  # tasks with at least one attempt
    merged: int = 0  # tasks whose attempt has a merge
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    agent_seconds: int = 0
    first_start: datetime | None = None
    last_end: datetime | None = None

    @property
    def tasks(self) -> int:
        return sum(self.statuses.values())


@dataclass(frozen=True)
class PlanningTotals:
    plans: int  # every plan run of the project, failed and replaced ones too
    cost: float
    recorded: int  # plans that kept their tokens and seconds (made after they were kept)
    input_tokens: int
    output_tokens: int
    cache_tokens: int
    seconds: float


@dataclass(frozen=True)
class AgentGroup:
    name: str  # a role or a model
    runs: int
    cost: float
    input_tokens: int
    output_tokens: int


def _mine(query, project_id: int):
    return query.join(StoryRun, StoryRun.id == SubTask.story_run_id).where(
        StoryRun.project_id == project_id
    )


def build_runs(session: Session, project_id: int) -> list[tuple[StoryRun, str | None]]:
    """The runs that were built, newest first, each with its story's title."""
    built = select(SubTask.story_run_id).distinct()
    query = (
        select(StoryRun, TrackerItem.summary)
        .outerjoin(TrackerItem, TrackerItem.key == StoryRun.story_key)
        .where(StoryRun.project_id == project_id, StoryRun.id.in_(built))
        .order_by(StoryRun.started_at.desc(), StoryRun.id.desc())
    )
    return [(run, title) for run, title in session.execute(query)]


def stories_approved(session: Session, project_id: int) -> int:
    """Stories with an approved plan, or that were ever built (a built run was approved first)."""
    built = select(SubTask.story_run_id).distinct()
    query = select(func.count(func.distinct(StoryRun.story_key))).where(
        StoryRun.project_id == project_id,
        (StoryRun.status == "approved") | StoryRun.id.in_(built),
    )
    return session.scalar(query) or 0


def usage_by_run(session: Session, project_id: int) -> dict[int, RunUsage]:
    """Each build run's tasks, attempts, merges and agent totals, by story_runs.id."""
    usage: dict[int, RunUsage] = {}

    def of(run_id: int) -> RunUsage:
        return usage.setdefault(run_id, RunUsage())

    statuses = _mine(
        select(SubTask.story_run_id, SubTask.status, func.count()), project_id
    ).group_by(SubTask.story_run_id, SubTask.status)
    for run_id, status, count in session.execute(statuses):
        of(run_id).statuses[status] = count

    attempts = _mine(
        select(
            SubTask.story_run_id,
            func.count(Attempt.id),
            func.count(func.distinct(Attempt.sub_task_id)),
            func.min(Attempt.started_at),
            func.max(Attempt.ended_at),
        ).join(Attempt, Attempt.sub_task_id == SubTask.id),
        project_id,
    ).group_by(SubTask.story_run_id)
    for run_id, count, tried, first, last in session.execute(attempts):
        row = of(run_id)
        row.attempts, row.tasks_tried, row.first_start, row.last_end = count, tried, first, last

    merged = _mine(
        select(SubTask.story_run_id, func.count(func.distinct(SubTask.id)))
        .join(Attempt, Attempt.sub_task_id == SubTask.id)
        .join(Merge, Merge.attempt_id == Attempt.id),
        project_id,
    ).group_by(SubTask.story_run_id)
    for run_id, count in session.execute(merged):
        of(run_id).merged = count

    agents = _mine(
        select(
            SubTask.story_run_id,
            func.sum(AgentRun.cost),
            func.sum(AgentRun.input_tokens),
            func.sum(AgentRun.output_tokens),
            func.sum(AgentRun.cache_tokens),
            func.sum(AgentRun.duration_s),
        )
        .join(Attempt, Attempt.sub_task_id == SubTask.id)
        .join(AgentRun, AgentRun.attempt_id == Attempt.id),
        project_id,
    ).group_by(SubTask.story_run_id)
    for run_id, cost, tokens_in, tokens_out, cache, seconds in session.execute(agents):
        row = of(run_id)
        row.cost, row.input_tokens, row.output_tokens = (
            float(cost or 0),
            tokens_in or 0,
            (tokens_out or 0),
        )
        row.cache_tokens, row.agent_seconds = cache or 0, seconds or 0
    return usage


def agents_grouped(session: Session, project_id: int, by_model: bool) -> list[AgentGroup]:
    """Every agent run of the project grouped by role, or by model; the dearest first."""
    key = (
        func.coalesce(AgentRun.model_used, AgentRun.model_requested, "unknown")
        if by_model
        else (AgentRun.role)
    )
    query = _mine(
        select(
            key,
            func.count(),
            func.sum(AgentRun.cost),
            func.sum(AgentRun.input_tokens),
            func.sum(AgentRun.output_tokens),
        )
        .select_from(AgentRun)
        .join(Attempt, Attempt.id == AgentRun.attempt_id)
        .join(SubTask, SubTask.id == Attempt.sub_task_id),
        project_id,
    ).group_by(key)
    groups = [
        AgentGroup(name, runs, float(cost or 0), tokens_in or 0, tokens_out or 0)
        for name, runs, cost, tokens_in, tokens_out in session.execute(query)
    ]
    return sorted(groups, key=lambda g: (-g.cost, g.name))


def planning_totals(session: Session, project_id: int) -> PlanningTotals:
    """What planning cost over every plan run, and how many of them kept tokens and seconds."""
    seen = StoryRun.plan_seconds.is_not(None)
    query = select(
        func.count(),
        func.sum(StoryRun.cost),
        func.count().filter(seen),
        func.sum(StoryRun.plan_input_tokens),
        func.sum(StoryRun.plan_output_tokens),
        func.sum(StoryRun.plan_cache_tokens),
        func.sum(StoryRun.plan_seconds),
    ).where(StoryRun.project_id == project_id)
    plans, cost, recorded, tokens_in, tokens_out, cache, seconds = session.execute(query).one()
    return PlanningTotals(
        plans, float(cost or 0), recorded, tokens_in or 0, tokens_out or 0, cache or 0, seconds or 0
    )
