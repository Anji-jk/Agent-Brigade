"""The background half of Plan and Re-plan.

A planning run takes minutes, so the request that starts it only makes the story_runs row
(status planning) and hands a PlanningJob to an executor. run_job then reads the story from
Jira, plans it (pipeline.planning) and writes the outcome on the row: waiting, with the plan
file, branch and cost; or failed, with the reason. A re-plan that succeeds also marks the row
it came from superseded. Nothing here raises: every stop ends as a failed row.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories.story_runs import FAILED, SUPERSEDED, WAITING, get_run
from core.settings import Settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from core.trackers.jira.story import read_story
from pipeline.planning.planner import NotReady, PlanningError, PlanResult, plan_story
from pipeline.planning.readiness import format_checks
from pipeline.planning.replan import replan_story
from pipeline.runner.claude_runner import AgentRunner

log = logging.getLogger(__name__)
MAX_ERROR_CHARS = 8000


@dataclass(frozen=True)
class PlanningJob:
    project_id: int
    story_key: str
    run_id: str
    budget: float | None
    previous_run_id: str | None = None  # set for a re-plan
    changes: str | None = None


@dataclass(frozen=True)
class JobContext:
    settings: Settings
    engine: Engine
    runner: AgentRunner
    client_factory: Callable[[Settings], JiraClient]
    now: Callable[[], datetime]


def _plan(job: PlanningJob, context: JobContext) -> PlanResult:
    client = context.client_factory(context.settings)
    try:
        story = read_story(client, job.story_key, context.settings.jira_project_key or None)
    finally:
        client.close()
    if job.previous_run_id:
        return replan_story(
            story,
            context.settings,
            context.runner,
            job.previous_run_id,
            job.changes or "",
            budget=job.budget,
            run_id=job.run_id,
        )
    return plan_story(story, context.settings, context.runner, budget=job.budget, run_id=job.run_id)


def _finish(job: PlanningJob, context: JobContext, result: PlanResult | None, error: str) -> None:
    with get_session(context.engine) as session:
        row = get_run(session, job.project_id, job.run_id)
        if row is None:  # deleted by hand while planning: nothing to record on
            return
        row.ended_at = context.now()
        if result is None:
            row.status, row.error = FAILED, error[:MAX_ERROR_CHARS]
            return
        row.status, row.error = WAITING, None
        row.plan_file = str(result.path)
        row.branch = result.record["config"]["branch"]
        row.cost = (result.record.get("planner") or {}).get("total_cost_usd")
        if job.previous_run_id:
            old = get_run(session, job.project_id, job.previous_run_id)
            if old is not None:
                old.status = SUPERSEDED


def run_job(job: PlanningJob, context: JobContext) -> None:
    """Plan (or re-plan) one story and record how it ended. Runs in a worker thread."""
    result, error = None, ""
    try:
        result = _plan(job, context)
    except NotReady as exc:
        error = format_checks(exc.checks)
    except PlanningError as exc:
        error = str(exc)
    except TrackerError as exc:
        error = f"Could not read {job.story_key} from Jira: {exc}"
    except Exception as exc:  # a worker thread has no one to raise to: keep it on the row
        log.exception("Planning run %s stopped unexpectedly", job.run_id)
        error = f"Planning stopped unexpectedly: {type(exc).__name__}: {exc}"
    _finish(job, context, result, error)
