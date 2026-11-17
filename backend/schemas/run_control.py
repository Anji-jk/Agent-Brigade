"""What the Start and the story-list endpoints give."""

from pydantic import BaseModel

from backend.schemas.publisher import UtcTime


class StartedOut(BaseModel):
    run_id: str
    state: str  # the build state right after launching: running
    pid: int
    started_at: str


class RunLineOut(BaseModel):
    run_id: str
    plan_status: str  # approved, superseded...
    build_state: str  # not_started | running | finished | stopped | paused | interrupted
    started_at: UtcTime
    ended_at: UtcTime
    cost: float  # what this run's agents cost


class StoryLineOut(BaseModel):
    key: str
    summary: str
    action: str  # start | running | continue | done: what the page offers for the approved run
    runs: list[RunLineOut]  # newest first


class TaskControlOut(BaseModel):
    run_id: str
    key: str
    state: str  # stopping | cancelling (the loop is acting) | stopped | cancelled (done)
    detail: str  # in words: what happens now, or where it resumes from


class StopAllOut(BaseModel):
    run_id: str
    stopping: list[str]  # the tasks that were running and are now being stopped


class ContinueOut(BaseModel):
    run_id: str
    continuing: list[str]  # the tasks that go on, each from the stage it had reached
    skipped: list[str]  # tasks that could not continue, each with the reason in words
    loop_started: bool  # True: no loop was running, so a new one was started on the same run
    detail: str  # in words: where each task resumes from
