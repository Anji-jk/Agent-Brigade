"""Start a story, stop or cancel its tasks, and the list of stories whose plan is approved."""

from fastapi import APIRouter, HTTPException, Request

from backend.schemas.run_control import (
    ContinueOut,
    StartedOut,
    StopAllOut,
    StoryLineOut,
    TaskControlOut,
)
from backend.services.planning_types import PlanningServiceError
from backend.services.run_control import RunControlService
from backend.services.task_continue import ContinueService
from backend.services.task_control import TaskControlService

router = APIRouter()


def service(request: Request) -> RunControlService:
    return request.app.state.run_control


@router.post("/runs/{run_id}/start")
def start(run_id: str, request: Request) -> StartedOut:
    try:
        return service(request).start(run_id)
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None


def tasks(request: Request) -> TaskControlService:
    return request.app.state.task_control


@router.post("/runs/{run_id}/tasks/{key}/stop")
def stop_task(run_id: str, key: str, request: Request) -> TaskControlOut:
    try:
        return tasks(request).stop(run_id, key)
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/runs/{run_id}/tasks/{key}/cancel")
def cancel_task(run_id: str, key: str, request: Request) -> TaskControlOut:
    try:
        return tasks(request).cancel(run_id, key)
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/runs/{run_id}/stop")
def stop_all(run_id: str, request: Request) -> StopAllOut:
    try:
        return tasks(request).stop_all(run_id)
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None


def continuing(request: Request) -> ContinueService:
    return request.app.state.task_continue


@router.post("/runs/{run_id}/tasks/{key}/continue")
def continue_task(run_id: str, key: str, request: Request) -> ContinueOut:
    try:
        return continuing(request).continue_task(run_id, key)
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/runs/{run_id}/continue")
def continue_run(run_id: str, request: Request) -> ContinueOut:
    try:
        return continuing(request).continue_run(run_id)
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.get("/orchestrator/stories")
def stories(request: Request) -> list[StoryLineOut]:
    try:
        return service(request).stories()
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None
