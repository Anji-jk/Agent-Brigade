"""How far a story run has got, and what its agents did: what the Orchestrator tab reads.

Reading only. The numbers come from the database (the loop writes them as it works) and the
tasks and their order from plan.json, so a task the loop has not reached yet is still listed,
as waiting. The event feeds come from the run's files (pipeline.feed), masked and cut.
"""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.schemas.orchestrator import AgentOut, AttemptOut, MergeOut, ProgressOut, TaskOut
from backend.services.run_lookup import find_run, project_root
from core.db import get_session
from core.db.models import StoryRun
from core.db.repositories.progress_rows import AttemptRows, TaskRows, rows_of_run
from core.runs import run_directory
from core.settings import Settings
from pipeline.control import continue_request
from pipeline.control import task_control as control
from pipeline.control.interrupted import notice
from pipeline.control.processes import CommandLine, command_line
from pipeline.control.state import build_state
from pipeline.feed import reports, sources
from pipeline.feed.items import feed
from pipeline.planning.plan_file import PlanFileError, load_plan

WAITING = "waiting"


def _agent(row: Any) -> AgentOut:
    return AgentOut(
        role=row.role,
        status=row.status,
        model=row.model_used or row.model_requested,
        effort=row.effort,
        turns=row.turns,
        cost=row.cost or 0.0,
        seconds=row.duration_s,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


class ProgressService:
    def __init__(
        self, settings: Settings, engine: Engine, lines: CommandLine = command_line
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._lines = lines

    # ---------- the state ----------

    def progress(self, run_id: str) -> ProgressOut:
        root = self._root()
        notice(
            self._engine, root, run_id, self._lines, quick=True
        )  # a dead loop's tasks become "stopped"
        with get_session(self._engine) as session:
            story = self._story(session, run_id)
            rows = rows_of_run(session, story.id)
        plan = self._plan(root, run_id)
        tasks = [self._task(root, run_id, one, rows) for one in plan] if plan else []
        known = {task.key for task in tasks}  # rows of tasks the plan does not list (not expected)
        tasks += [
            self._task(root, run_id, {"key": r.sub_task.key}, rows)
            for r in rows
            if r.sub_task.key not in known
        ]
        return ProgressOut(
            run_id=run_id,
            story_key=story.story_key,
            status=story.status,
            build_state=build_state(run_directory(root, run_id), run_id, self._lines, quick=True),
            branch=story.branch,
            budget=story.budget,
            cost=sum(task.cost for task in tasks),
            started_at=story.started_at,
            ended_at=story.ended_at,
            tasks=tasks,
        )

    def _task(self, root: Path, run_id: str, planned: dict, rows: list[TaskRows]) -> TaskOut:
        mine = next((r for r in rows if r.sub_task.key == planned["key"]), None)
        attempts = (
            [self._attempt(root, run_id, planned["key"], a) for a in mine.attempts] if mine else []
        )
        sub = mine.sub_task if mine else None
        return TaskOut(
            key=planned["key"],
            title=planned.get("title"),
            depends_on=planned.get("depends_on", []),
            status=sub.status if sub else WAITING,
            stage=sub.current_stage if sub else None,
            control=self._control(root, run_id, planned["key"]),
            size=sub.size if sub else None,
            cost=sum(agent.cost for attempt in attempts for agent in attempt.agents),
            attempts=attempts,
        )

    @staticmethod
    def _control(root: Path, run_id: str, key: str) -> str | None:
        """What a person told this task: asked and not yet done (-ing), or settled."""
        folder = run_directory(root, run_id)
        asked = control.pending(folder, key)
        if asked:
            return "stopping" if asked == control.STOP else "cancelling"
        settled = control.settled(folder, key)
        if settled:
            return settled.state
        return "continuing" if continue_request.wanted(folder, key) is not None else None

    def _attempt(self, root: Path, run_id: str, key: str, rows: AttemptRows) -> AttemptOut:
        attempt, merge = rows.attempt, rows.merge
        return AttemptOut(
            number=attempt.number,
            outcome=attempt.outcome,
            reason=attempt.reason,
            branch=attempt.branch,
            commit=attempt.commit_sha,
            started_at=attempt.started_at,
            ended_at=attempt.ended_at,
            agents=[_agent(row) for row in rows.agents],
            merge=MergeOut(kind=merge.kind, commit=merge.commit, merged_at=merge.merged_at)
            if merge
            else None,
            sources=sources.available(root, run_id, key, attempt.number),
        )

    # ---------- the event feeds ----------

    def story_log(self, run_id: str, after: int, full: bool) -> dict[str, Any]:
        root = self._root()
        with get_session(self._engine) as session:
            self._story(session, run_id)
        return feed(sources.story_log_items(root, run_id), after, full=full)

    def attempt_events(
        self, run_id: str, key: str, number: int, source: str, after: int, full: bool
    ) -> dict[str, Any]:
        root = self._root()
        with get_session(self._engine) as session:
            self._story(session, run_id)
        items = sources.attempt_items(root, run_id, key, number, source)
        return {
            **feed(items, after, full=full),
            "sources": sources.available(root, run_id, key, number),
        }

    def stage_report(self, run_id: str, key: str, number: int, stage: str) -> dict[str, Any]:
        """What the agent of `stage` (build, test, judge) did, from its report."""
        root = self._root()
        with get_session(self._engine) as session:
            self._story(session, run_id)
        return reports.stage_report(root, run_id, key, number, stage)

    # ---------- helpers ----------

    def _root(self) -> Path:
        return project_root(self._settings)

    def _story(self, session: Session, run_id: str) -> StoryRun:
        return find_run(session, self._settings, run_id)

    @staticmethod
    def _plan(root: Path, run_id: str) -> list[dict]:
        """The plan's tasks as {key, title, depends_on (keys)}; none when there is no plan."""
        try:
            tasks = load_plan(root, run_id)["tasks"]
        except (PlanFileError, KeyError):
            return []
        keys = {t["id"]: t.get("jira_key") or t["id"] for t in tasks}
        return [
            {
                "key": keys[t["id"]],
                "title": t.get("title"),
                "depends_on": [keys.get(d, d) for d in t.get("depends_on", [])],
            }
            for t in tasks
        ]
