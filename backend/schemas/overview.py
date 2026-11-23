"""What the Overview endpoint gives: the project's runs added up. Times are UTC."""

from pydantic import BaseModel

from backend.schemas.publisher import UtcTime


class RunsOut(BaseModel):
    total: int  # build runs
    by_state: dict[str, int]  # finished | running | stopped | failed | interrupted
    stories_approved: int  # stories with an approved plan, or ever built
    stories: int  # stories that have a build run
    stories_complete: int  # their newest run finished
    stories_active: int  # their newest run is running


class TasksOut(BaseModel):
    planned: int
    merged: int
    attempts: int
    retries: int  # attempts beyond the first of a task


class CostOut(BaseModel):
    build: float
    planning: float  # every plan run, failed and replaced ones too
    total: float


class TokensOut(BaseModel):
    input: int
    output: int
    cache: int  # counted apart, which is why input looks small
    planning_plans: int  # plan runs
    planning_recorded: int  # of those, how many kept their tokens (the rest: "not recorded")


class TimeOut(BaseModel):
    wall_clock_seconds: int  # each run's first attempt start to last attempt end, added up
    agent_seconds: int  # what the agents worked; parallel tasks make this longer than the above
    planning_seconds: float  # only plans that recorded it


class GroupOut(BaseModel):
    name: str
    runs: int
    cost: float
    input_tokens: int
    output_tokens: int


class RunRowOut(BaseModel):
    run_id: str
    story_key: str
    title: str | None
    state: str
    tasks_merged: int
    tasks_planned: int
    planned_from: str  # plan | database (the plan file was missing)
    attempts: int
    input_tokens: int
    output_tokens: int
    cost: float  # build + this run's planning
    wall_clock_seconds: int
    started_at: UtcTime


class OverviewOut(BaseModel):
    runs: RunsOut
    tasks: TasksOut
    cost: CostOut
    tokens: TokensOut
    time: TimeOut
    by_role: list[GroupOut]  # builder, tester, reviewer... and planner (cost and tokens)
    by_model: list[GroupOut]  # build agents only: a plan's model is not kept


class RunPageOut(BaseModel):
    """One page of the runs, newest first: page 0 is the newest."""

    total: int  # build runs in all
    page: int  # a page past the end is answered with the last one, so this is the real one
    pages: int
    size: int
    items: list[RunRowOut]
