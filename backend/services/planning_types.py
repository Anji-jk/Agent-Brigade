"""What the planning service hands back, and the errors it raises (each knows its HTTP status)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from core.db.models import StoryRun

STOPPED = "Brigade stopped while this run was planning. Plan the story again."


class PlanningServiceError(Exception):
    status = 400


class NotFound(PlanningServiceError):
    status = 404


class Conflict(PlanningServiceError):
    status = 409


class Executor(Protocol):
    def submit(self, fn: Callable[..., Any], /, *args: Any) -> Any: ...


@dataclass(frozen=True)
class RunView:
    row: StoryRun
    plan: dict[str, Any] | None  # plan.json, once the run has one
    plan_error: str | None = None  # why a plan file that should be there could not be read


def run_id_of(row: StoryRun) -> str:
    """The run id of a row this service made: it always sets one."""
    if row.run_id is None:
        raise PlanningServiceError(f"Run row {row.id} has no run id.")
    return row.run_id
