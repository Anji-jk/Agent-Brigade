"""Start a story from the page, and list the stories that can be started.

Start launches the story loop as its own process (pipeline.control.launch), so a restart of this
server never kills a story that is spending money. What a run is doing now is read from that
process and the loop's files (pipeline.control.state), never from a saved status.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine, select

from backend.schemas.run_control import RunLineOut, StartedOut, StoryLineOut
from backend.services.planning_types import Conflict
from backend.services.run_lookup import find_run, project_root
from core.db import get_session
from core.db.models import TrackerItem
from core.db.repositories import story_runs as runs
from core.db.repositories.progress_rows import rows_of_run
from core.db.repositories.projects import sync_env_project
from core.runs import run_directory
from core.settings import Settings
from pipeline.control import state as states
from pipeline.control.launch import Launch, launch_loop
from pipeline.control.processes import CommandLine, command_line
from pipeline.stages.prepare import PrepareError, approved_plan

Launcher = Callable[[Path, str, Path], Launch]
BRIGADE_FOLDER = Path(__file__).resolve().parents[2]  # where `python -m pipeline.stages` runs
OFFER = {  # what the page offers, by build state
    states.NOT_STARTED: "start",
    states.RUNNING: "running",
    states.FINISHED: "done",
    states.STOPPED: "continue",
    states.PAUSED: "continue",
    states.INTERRUPTED: "continue",
}
REFUSED = {
    states.RUNNING: "Run {run_id} is already running.",
    states.FINISHED: "Run {run_id} has already finished: every task is merged.",
    states.STOPPED: "Run {run_id} was started before and stopped with tasks not merged: "
    "it is continued, not started again (Continue).",
    states.PAUSED: "Run {run_id} was paused: a task was stopped on request "
    "(Continue goes on from where it stopped).",
    states.INTERRUPTED: "Run {run_id} was started before and its process is gone: "
    "it is continued, not started again (Continue).",
}


class RunControlService:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        launcher: Launcher = launch_loop,
        lines: CommandLine = command_line,
    ) -> None:
        self._settings, self._engine = settings, engine
        self._launch, self._lines = launcher, lines
        self._one_start_at_a_time = threading.Lock()

    def start(self, run_id: str) -> StartedOut:
        root = project_root(self._settings)
        with self._one_start_at_a_time, get_session(self._engine) as session:
            row = find_run(session, self._settings, run_id)
            if row.status != runs.APPROVED:
                raise Conflict(f"Run {run_id} is {row.status}: only an approved plan is started.")
            try:
                approved_plan(root, run_id)
            except PrepareError as exc:
                raise Conflict(str(exc)) from None
            folder = run_directory(root, run_id)
            now = states.build_state(folder, run_id, self._lines)
            if now != states.NOT_STARTED:
                raise Conflict(REFUSED[now].format(run_id=run_id))
            launch = self._launch(folder, run_id, BRIGADE_FOLDER)
        return StartedOut(
            run_id=run_id,
            state=states.build_state(folder, run_id, self._lines),
            pid=launch.pid,
            started_at=launch.started_at,
        )

    def stories(self) -> list[StoryLineOut]:
        """The stories that have an approved plan, each with its runs (newest first)."""
        root = project_root(self._settings)
        with get_session(self._engine) as session:
            project = sync_env_project(session, self._settings)
            if project is None:
                return []
            keys = runs.story_keys_with_status(session, project.id, runs.APPROVED)
            summaries = dict(
                session.execute(
                    select(TrackerItem.key, TrackerItem.summary).where(TrackerItem.key.in_(keys))
                ).all()
            )
            return [
                self._line(session, root, key, summaries.get(key, ""), project.id) for key in keys
            ]

    def _line(self, session, root: Path, key: str, summary: str, project_id: int) -> StoryLineOut:
        lines = []
        for row in runs.runs_of_story(session, project_id, key):
            if row.run_id is None:
                continue
            built = states.build_state(
                run_directory(root, row.run_id), row.run_id, self._lines, quick=True
            )
            spent = sum(
                agent.cost or 0.0
                for task in rows_of_run(session, row.id)
                for attempt in task.attempts
                for agent in attempt.agents
            )
            lines.append(
                RunLineOut(
                    run_id=row.run_id,
                    plan_status=row.status,
                    build_state=built,
                    started_at=row.started_at,
                    ended_at=row.ended_at,
                    cost=spent,
                )
            )
        approved = next((one for one in lines if one.plan_status == runs.APPROVED), None)
        action = OFFER[approved.build_state] if approved else "done"
        return StoryLineOut(key=key, summary=summary, action=action, runs=lines)
