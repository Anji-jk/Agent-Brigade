"""What all the runs of the project add up to: the Orchestrator's Overview tab. Reading only.

The sums come from the database (core.db.repositories.overview_rows). Two small reads of files
sit on top, both with a fallback: a run's planned task count from its plan.json (a plan lists
tasks the loop never reached; the file is read once and the count kept), and, for a run the
database shows unfinished, whether its loop is still alive (build_state). The page asks every
few seconds, so no process is looked at: a loop is alive when its heartbeat is fresh.
"""

from pathlib import Path

from sqlalchemy import Engine

from backend.schemas.overview import (
    CostOut,
    GroupOut,
    OverviewOut,
    RunPageOut,
    RunRowOut,
    RunsOut,
    TasksOut,
    TimeOut,
    TokensOut,
)
from backend.services.run_lookup import project_root
from core.db import get_session
from core.db.models import StoryRun
from core.db.repositories import overview_rows as rows
from core.db.repositories.projects import sync_env_project
from core.runs import run_directory
from core.settings import Settings
from pipeline.control import state
from pipeline.planning.plan_file import PlanFileError, load_plan

FINISHED, RUNNING, STOPPED, FAILED, INTERRUPTED = (
    "finished",
    "running",
    "stopped",
    "failed",
    "interrupted",
)
_PLANNED: dict[tuple[Path, str], int] = {}  # (project, run id) -> tasks in its plan, once read


def _no_process(_pid: int) -> None:
    return None


def planned_tasks(root: Path, run_id: str) -> int | None:
    """How many tasks the run's plan lists; None when the plan file cannot be read."""
    if (root, run_id) not in _PLANNED:
        try:
            _PLANNED[(root, run_id)] = len(load_plan(root, run_id)["tasks"])
        except (PlanFileError, KeyError, TypeError):
            return None
    return _PLANNED[(root, run_id)]


def run_state(root: Path, run_id: str, usage: rows.RunUsage, planned: int) -> str:
    if planned and usage.merged >= planned:
        return FINISHED
    built = state.build_state(run_directory(root, run_id), run_id, _no_process, quick=True)
    if built in (state.RUNNING, state.INTERRUPTED, state.FINISHED):
        return built
    return FAILED if usage.statuses.get("error") else STOPPED


def _seconds(usage: rows.RunUsage) -> int:
    if usage.first_start is None or usage.last_end is None:
        return 0
    return max(0, int((usage.last_end - usage.first_start).total_seconds()))


def _group(one: rows.AgentGroup) -> GroupOut:
    return GroupOut(**one.__dict__)


class OverviewService:
    def __init__(self, settings: Settings, engine: Engine) -> None:
        self._settings = settings
        self._engine = engine

    def overview(self) -> OverviewOut:
        root = project_root(self._settings)
        with get_session(self._engine) as session:
            project = sync_env_project(session, self._settings)
            pid = project.id if project else 0
            runs = rows.build_runs(session, pid)
            usage = rows.usage_by_run(session, pid)
            planning = rows.planning_totals(session, pid)
            approved = rows.stories_approved(session, pid)
            roles = [_group(g) for g in rows.agents_grouped(session, pid, by_model=False)]
            models = [_group(g) for g in rows.agents_grouped(session, pid, by_model=True)]
            table = [self._row(root, run, title, usage[run.id]) for run, title in runs]
        return self._put_together(table, usage, planning, roles, models, approved)

    def run_page(self, page: int, size: int) -> RunPageOut:
        """One page of the runs, newest first; only this page's rows are built."""
        root = project_root(self._settings)
        with get_session(self._engine) as session:
            project = sync_env_project(session, self._settings)
            pid = project.id if project else 0
            runs = rows.build_runs(session, pid)
            usage = rows.usage_by_run(session, pid) if runs else {}
            pages = max(1, -(-len(runs) // size))
            page = min(page, pages - 1)
            chosen = runs[page * size : (page + 1) * size]
            items = [self._row(root, run, title, usage[run.id]) for run, title in chosen]
        return RunPageOut(total=len(runs), page=page, pages=pages, size=size, items=items)

    @staticmethod
    def _row(root: Path, run: StoryRun, title: str | None, use: rows.RunUsage) -> RunRowOut:
        from_plan = planned_tasks(root, run.run_id or "")
        planned = use.tasks if from_plan is None else from_plan
        return RunRowOut(
            run_id=run.run_id or "",
            story_key=run.story_key,
            title=title,
            state=run_state(root, run.run_id or "", use, planned),
            tasks_merged=use.merged,
            tasks_planned=planned,
            planned_from="database" if from_plan is None else "plan",
            attempts=use.attempts,
            input_tokens=use.input_tokens + (run.plan_input_tokens or 0),
            output_tokens=use.output_tokens + (run.plan_output_tokens or 0),
            cost=use.cost + (run.cost or 0.0),
            wall_clock_seconds=_seconds(use),
            started_at=run.started_at,
        )

    @staticmethod
    def _put_together(
        table: list[RunRowOut],
        usage: dict[int, rows.RunUsage],
        planning: rows.PlanningTotals,
        roles: list[GroupOut],
        models: list[GroupOut],
        approved: int,
    ) -> OverviewOut:
        every = list(usage.values())
        by_state: dict[str, int] = {}
        newest: dict[
            str, str
        ] = {}  # story key -> the state of its newest run (the list is newest first)
        for one in table:
            by_state[one.state] = by_state.get(one.state, 0) + 1
            newest.setdefault(one.story_key, one.state)
        build = sum(u.cost for u in every)
        if planning.plans:
            roles.append(
                GroupOut(
                    name="planner",
                    runs=planning.plans,
                    cost=planning.cost,
                    input_tokens=planning.input_tokens,
                    output_tokens=planning.output_tokens,
                )
            )
        return OverviewOut(
            runs=RunsOut(
                total=len(table),
                stories_approved=approved,
                by_state=by_state,
                stories=len(newest),
                stories_complete=sum(1 for s in newest.values() if s == FINISHED),
                stories_active=sum(1 for s in newest.values() if s == RUNNING),
            ),
            tasks=TasksOut(
                planned=sum(one.tasks_planned for one in table),
                merged=sum(u.merged for u in every),
                attempts=sum(u.attempts for u in every),
                retries=sum(max(0, u.attempts - u.tasks_tried) for u in every),
            ),
            cost=CostOut(build=build, planning=planning.cost, total=build + planning.cost),
            tokens=TokensOut(
                input=sum(u.input_tokens for u in every) + planning.input_tokens,
                output=sum(u.output_tokens for u in every) + planning.output_tokens,
                cache=sum(u.cache_tokens for u in every) + planning.cache_tokens,
                planning_plans=planning.plans,
                planning_recorded=planning.recorded,
            ),
            time=TimeOut(
                wall_clock_seconds=sum(one.wall_clock_seconds for one in table),
                agent_seconds=sum(u.agent_seconds for u in every),
                planning_seconds=planning.seconds,
            ),
            by_role=sorted(roles, key=lambda g: (-g.cost, g.name)),
            by_model=models,
        )
