"""What the Orchestrator endpoints give. Times are UTC (see schemas/publisher.py)."""

from pydantic import BaseModel

from backend.schemas.publisher import UtcTime


class AgentOut(BaseModel):
    role: str  # builder | tester | reviewer
    status: str | None  # running | done | error
    model: str | None
    effort: str | None
    turns: int | None
    cost: float
    seconds: int | None
    started_at: UtcTime
    ended_at: UtcTime


class MergeOut(BaseModel):
    kind: str  # fast-forward | real
    commit: str | None
    merged_at: UtcTime


class AttemptOut(BaseModel):
    number: int
    outcome: str | None
    reason: str | None
    branch: str | None
    commit: str | None
    started_at: UtcTime
    ended_at: UtcTime
    agents: list[AgentOut]
    merge: MergeOut | None
    sources: list[str]  # the event files this attempt has written: orchestrator, builder...


class TaskOut(BaseModel):
    key: str
    title: str | None  # from the plan
    depends_on: list[str]
    status: str  # waiting until the loop reaches it, then the sub_tasks status
    stage: str | None
    control: str | None  # a person's word: stopping | cancelling | stopped | cancelled
    size: str | None
    cost: float
    attempts: list[AttemptOut]


class ProgressOut(BaseModel):
    run_id: str
    story_key: str
    status: str  # the plan's: approved, superseded...
    build_state: str  # not_started | running | finished | stopped | paused | interrupted
    branch: str | None
    budget: float | None
    cost: float  # what the agents of this run cost so far
    started_at: UtcTime
    ended_at: UtcTime
    tasks: list[TaskOut]