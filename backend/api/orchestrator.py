"""Orchestrator endpoints: how a story run is going, and what it did. Reading only.

The page asks for the state now and then, and for the event feeds with `after` set to the
`next` of its last answer, so it gets only what is new.
"""

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request

from backend.schemas.orchestrator import ProgressOut
from backend.services.planning_types import PlanningServiceError
from backend.services.progress import ProgressService
from pipeline.feed.sources import FeedError

router = APIRouter()
T = TypeVar("T")
After = Query(0, ge=0, description="The index to start from: the `next` of the last answer.")
Full = Query(False, description="Do not cut long texts (secrets are still masked).")


def service(request: Request) -> ProgressService:
    return request.app.state.progress


def run(action: Callable[[], T]) -> T:
    try:
        return action()
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except FeedError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/runs/{run_id}/progress")
def progress(run_id: str, request: Request) -> ProgressOut:
    return run(lambda: service(request).progress(run_id))


@router.get("/runs/{run_id}/log")
def story_log(
    run_id: str, request: Request, after: int = After, full: bool = Full
) -> dict[str, Any]:
    return run(lambda: service(request).story_log(run_id, after, full))


@router.get("/runs/{run_id}/tasks/{key}/attempts/{number}/events")
def attempt_events(
    run_id: str,
    key: str,
    number: int,
    request: Request,
    source: str = "orchestrator",
    after: int = After,
    full: bool = Full,
) -> dict[str, Any]:
    return run(lambda: service(request).attempt_events(run_id, key, number, source, after, full))