"""What the Planning endpoints take and give. Times are UTC (see schemas/publisher.py)."""

from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.publisher import UtcTime

Dollars = Field(default=None, gt=0, allow_inf_nan=False)


class PlanIn(BaseModel):
    budget: float | None = Dollars  # for planning and building the whole story


class ReplanIn(BaseModel):
    changes: str = Field(min_length=1, max_length=4000)  # your own idea for the new plan
    budget: float | None = Dollars  # empty: the budget of the run it comes from


class SyncOut(BaseModel):
    space: str
    epics: int
    stories: int
    subtasks: int
    added: int
    updated: int
    unchanged: int
    removed: int
    kept: int
    synced_at: UtcTime
    summary: str


class RunSummaryOut(BaseModel):
    run_id: str
    story_key: str
    status: str  # planning | waiting | approved | superseded | failed
    budget: float | None
    cost: float | None
    branch: str | None
    error: str | None
    started_at: UtcTime
    ended_at: UtcTime


class RunOut(RunSummaryOut):
    plan: dict[str, Any] | None  # plan.json, once the run has one
    plan_error: str | None
    run_as: dict[str, str]  # task id -> what its size gets, e.g. "sonnet, low effort, ..."
    task_limits_usd: float | None  # the tasks' spending limits added up


class ItemOut(BaseModel):
    key: str
    summary: str
    status: str | None


class RunBrief(BaseModel):
    run_id: str
    status: str
    started_at: UtcTime


class StoryOut(ItemOut):
    subtasks: list[ItemOut]
    latest_run: RunBrief | None


class EpicOut(BaseModel):
    key: str | None  # None: stories whose epic is not on the board
    summary: str
    status: str | None
    stories: list[StoryOut]


class TreeOut(BaseModel):
    space: str
    last_synced: UtcTime
    epics: list[EpicOut]


class CheckOut(BaseModel):
    group: str  # Story | Checkout | Project | Tests
    status: str  # ok | failed | warning | skipped
    what: str
    detail: str


class ChecksOut(BaseModel):
    story_key: str
    folder: str
    base_branch: str
    ready: bool
    checks: list[CheckOut]
    text: str  # the same checks as text, as the command line prints them
