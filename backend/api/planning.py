"""Planning endpoints. Plain `def` handlers run in worker threads; Plan and Re-plan answer at
once (202) and plan in the background, so ask GET /api/runs/{run_id} for the outcome."""

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Request

from backend.schemas.planning import (
    CheckOut,
    ChecksIn,
    ChecksOut,
    EpicOut,
    ItemOut,
    PlanIn,
    ReplanIn,
    RunBrief,
    RunOut,
    RunSummaryOut,
    StoryOut,
    SyncOut,
    TreeOut,
)
from backend.services.planning import PlanningService, PlanningServiceError, RunView, run_id_of
from core.db.models import StoryRun
from core.trackers.errors import TrackerError
from core.trackers.jira.story import StoryError
from core.trackers.jira.sync import SyncError
from pipeline.planning.approval import ApprovalError, JiraWriteError
from pipeline.planning.profiles import profile_for
from pipeline.planning.readiness import format_checks
from pipeline.workspace.git import GitError

router = APIRouter()
T = TypeVar("T")


def service(request: Request) -> PlanningService:
    return request.app.state.planning


def run(action: Callable[[], T]) -> T:
    """The service call, with its errors turned into HTTP answers the page can show."""
    try:
        return action()
    except PlanningServiceError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except (StoryError, SyncError, GitError) as exc:
        raise HTTPException(400, str(exc)) from None
    except JiraWriteError as exc:
        raise HTTPException(502, str(exc)) from None
    except ApprovalError as exc:
        raise HTTPException(409, str(exc)) from None
    except TrackerError as exc:
        raise HTTPException(502, str(exc)) from None


def summary_out(row: StoryRun) -> RunSummaryOut:
    return RunSummaryOut(
        run_id=run_id_of(row),
        story_key=row.story_key,
        status=row.status,
        budget=row.budget,
        cost=row.cost,
        branch=row.branch,
        error=row.error,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def run_out(view: RunView) -> RunOut:
    tasks = (view.plan or {}).get("tasks") or []
    sizes = {task["id"]: profile_for(task["complexity"]) for task in tasks}
    return RunOut(
        **summary_out(view.row).model_dump(),
        plan=view.plan,
        plan_error=view.plan_error,
        run_as={task_id: size.describe() for task_id, size in sizes.items()},
        task_limits_usd=sum(size.max_budget_usd for size in sizes.values()) if sizes else None,
    )


@router.post("/tracker/sync")
def sync(request: Request) -> SyncOut:
    result = run(service(request).sync)
    counts = result.counts
    return SyncOut(
        space=result.space,
        epics=result.epics,
        stories=result.stories,
        subtasks=result.subtasks,
        added=counts.added,
        updated=counts.updated,
        unchanged=counts.unchanged,
        removed=counts.removed,
        kept=counts.kept,
        synced_at=result.synced_at,
        summary=result.describe(),
    )


@router.get("/tracker/tree")
def tree(request: Request) -> TreeOut:
    view = run(service(request).tree)

    def item(row) -> ItemOut:
        return ItemOut(key=row.key, summary=row.summary, status=row.status)

    def story(node) -> StoryOut:
        latest = node.latest_run
        return StoryOut(
            **item(node.item).model_dump(),
            subtasks=[item(sub) for sub in node.subtasks],
            latest_run=RunBrief(
                run_id=latest.run_id, status=latest.status, started_at=latest.started_at
            )
            if latest
            else None,
        )

    epics = [
        EpicOut(
            key=e.key, summary=e.summary, status=e.status, stories=[story(s) for s in e.stories]
        )
        for e in view.epics
    ]
    return TreeOut(space=view.space, last_synced=view.last_synced, epics=epics)


@router.post("/stories/{key}/checks")
def checks(key: str, request: Request, body: ChecksIn | None = None) -> ChecksOut:
    planning = service(request)
    result = run(lambda: planning.checks(key, bool(body and body.run_tests)))
    folder, base_branch = planning.checks_context()
    return ChecksOut(
        story_key=result.story_key,
        folder=folder,
        base_branch=base_branch,
        ready=result.ready,
        checks=[
            CheckOut(group=c.group, status=c.status, what=c.what, detail=c.detail)
            for c in result.checks
        ],
        text=format_checks(result),
    )


@router.post("/stories/{key}/plan", status_code=202)
def plan(key: str, request: Request, body: PlanIn | None = None) -> RunSummaryOut:
    budget = body.budget if body else None
    return summary_out(run(lambda: service(request).plan(key, budget)))


@router.get("/stories/{key}/runs")
def story_runs(key: str, request: Request) -> list[RunSummaryOut]:
    return [summary_out(row) for row in run(lambda: service(request).story_runs(key))]


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> RunOut:
    return run_out(run(lambda: service(request).run(run_id)))


@router.post("/runs/{run_id}/replan", status_code=202)
def replan(run_id: str, body: ReplanIn, request: Request) -> RunSummaryOut:
    return summary_out(run(lambda: service(request).replan(run_id, body.changes, body.budget)))


@router.post("/runs/{run_id}/approve")
def approve(run_id: str, request: Request) -> RunOut:
    return run_out(run(lambda: service(request).approve(run_id)))
