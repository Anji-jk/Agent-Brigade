"""What Jira should show for a story run, worked out from what the loop knows. No Jira here.

The rules are the table of the technical document (12.1): the database decides, Jira follows.
Every comment has an id, so the mirror writes each one once however often it runs.
"""

from dataclasses import dataclass

from core.trackers.jira.names import (
    DONE,
    ERROR,
    IN_PROGRESS,
    IN_REVIEW,
    LABEL_BLOCKED,
    LABEL_ERROR,
    LABEL_STOPPED,
    LABEL_UNMERGED,
    TODO,
)
from pipeline.stages.story_report import (
    BLOCKED,
    CANCELLED,
    FAILED,
    MERGED,
    NEEDS_PERSON,
    PAUSED,
)


@dataclass(frozen=True)
class TaskFacts:
    key: str
    status: str  # a story_report status: merged, failed, blocked, waiting ...
    attempts: int
    running: bool
    detail: str = ""
    cost: float = 0.0


@dataclass(frozen=True)
class StoryFacts:
    key: str
    epic: str | None
    branch: str
    tasks: list[TaskFacts]
    finished: bool  # the loop has ended
    report: str  # the story report as text


@dataclass(frozen=True)
class Wanted:
    status: str  # a meaning of core.trackers.jira.names
    labels: tuple[str, ...] = ()
    comments: tuple[tuple[str, str], ...] = ()  # (id, text)
    only_from_todo: bool = False  # move it only when it is still To Do


def _task(t: TaskFacts) -> Wanted:
    if t.running:
        text = f"Attempt {t.attempts} started."
        return Wanted(IN_PROGRESS, (), ((f"{t.key}:attempt:{t.attempts}", text),))
    if t.status == MERGED:
        how = f"after {t.attempts} attempt(s)" if t.attempts else "in an earlier run"
        text = f"Merged into the story branch {how}. Cost ${t.cost:.4f}."
        return Wanted(DONE, (), ((f"{t.key}:merged", text),))
    if t.status == FAILED:
        text = f"Failed after {t.attempts} attempt(s): {t.detail}"
        return Wanted(ERROR, (), ((f"{t.key}:failed", text),))
    if t.status in (PAUSED, CANCELLED, NEEDS_PERSON):
        said = {PAUSED: "Stopped", CANCELLED: "Cancelled", NEEDS_PERSON: "Needs a person"}
        text = f"{said[t.status]} at attempt {t.attempts}: {t.detail or 'on request'}"
        return Wanted(IN_PROGRESS, (LABEL_STOPPED,), ((f"{t.key}:{t.status}:{t.attempts}", text),))
    if t.status == BLOCKED:
        return Wanted(TODO, (LABEL_BLOCKED,), ((f"{t.key}:blocked", t.detail),))
    return Wanted(IN_PROGRESS if t.attempts else TODO)


def _story(facts: StoryFacts) -> Wanted:
    # A task settled by an earlier run shows no attempt now, but the story has started.
    settled = {MERGED, FAILED, NEEDS_PERSON, PAUSED, CANCELLED}
    started = any(t.attempts or t.running or t.status in settled for t in facts.tasks)
    if not started:
        return Wanted(TODO)
    begun = (
        "story:started",
        f"Agent Brigade started building on branch {facts.branch}: "
        f"{len(facts.tasks)} sub-task(s) planned.",
    )
    states = {t.status for t in facts.tasks}
    if facts.finished and states == {MERGED}:
        return Wanted(
            IN_REVIEW, (LABEL_UNMERGED,), (begun, ("story:report:unmerged", facts.report))
        )
    if facts.finished and FAILED in states:
        return Wanted(IN_REVIEW, (LABEL_ERROR,), (begun, ("story:report:error", facts.report)))
    return Wanted(IN_PROGRESS, (), (begun,))


def wanted_for(facts: StoryFacts) -> dict[str, Wanted]:
    """Sub-tasks first, then the story, then its epic: the order the mirror writes them."""
    found = {t.key: _task(t) for t in facts.tasks}
    story = _story(facts)
    found[facts.key] = story
    if facts.epic:
        found[facts.epic] = Wanted(TODO if story.status == TODO else IN_PROGRESS, (), (), True)
    return found
