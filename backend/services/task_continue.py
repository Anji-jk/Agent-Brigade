"""Continue a stopped task, or every stopped task of a run, and find an interrupted one.

A task a person stopped, or one a dead loop left in the middle, goes on in the *same attempt*
(its worktree, branch, reports and row), from the first stage it had not finished. This service
checks that it may, takes the Stop back and leaves a note naming the attempt
(pipeline.control.continue_request); the story loop does the work. If no loop is running, a new
one is started on the same run (``story.lock`` keeps it to one).

Refused: a task that is merged, cancelled, still running, not stopped, whose worktree or branch
is gone, or whose run has spent its budget. Nothing is spent by refusing.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine

from backend.schemas.run_control import ContinueOut
from backend.services.planning_types import Conflict, NotFound
from backend.services.run_control import BRIGADE_FOLDER, Launcher
from backend.services.run_lookup import find_run, project_root
from core.db import get_session
from core.db.repositories import merge_rows
from core.db.repositories.progress_rows import rows_of_run
from core.runs import run_directory
from core.settings import Settings
from pipeline.control import continue_request
from pipeline.control import task_control as control
from pipeline.control.interrupted import clear_stale_lock, notice
from pipeline.control.launch import launch_loop, loop_alive
from pipeline.control.processes import CommandLine, command_line
from pipeline.planning.plan_file import PlanFileError, load_plan
from pipeline.stages import checkpoint
from pipeline.stages.attempt_resume import resume_ready
from pipeline.stages.errors import BuildError
from pipeline.stages.schedule import MERGED, task_states
from pipeline.workspace.commands import kill_tree

OPEN = (None, "built", "stopped")  # outcomes of an attempt that a Continue may pick up


class ContinueService:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        launcher: Launcher = launch_loop,
        lines: CommandLine = command_line,
        kill: Callable = kill_tree,
    ) -> None:
        self._settings, self._engine = settings, engine
        self._launch, self._lines, self._kill = launcher, lines, kill
        self._one_at_a_time = threading.Lock()

    def continue_task(self, run_id: str, key: str) -> ContinueOut:
        with self._one_at_a_time:
            root, folder, budget_left = self._open(run_id)
            if key not in self._plan_keys(root, run_id):
                raise NotFound(f"Run {run_id} has no task {key}.")
            number, stage = self._check(root, folder, run_id, key, budget_left)
            return self._go([(key, number, stage)], [], run_id, root, folder)

    def continue_run(self, run_id: str) -> ContinueOut:
        with self._one_at_a_time:
            root, folder, budget_left = self._open(run_id)
            ready, skipped = [], []
            for key in self._plan_keys(root, run_id):
                if not (control.settled(folder, key) or continue_request.wanted(folder, key)):
                    continue
                try:
                    ready.append((key, *self._check(root, folder, run_id, key, budget_left)))
                except Conflict as exc:
                    skipped.append(f"{key}: {exc}")
            if not ready:
                why = " ".join(skipped) or "No task is stopped, so there is nothing to continue."
                raise Conflict(f"Run {run_id}: {why}")
            return self._go(ready, skipped, run_id, root, folder)

    # ---------- helpers ----------

    def _open(self, run_id: str) -> tuple[Path, Path, bool]:
        """(the project, the run's folder, is there budget left). Finds interrupted tasks first,
        so that a run whose loop died can be continued without anyone reading it before."""
        root = project_root(self._settings)
        with get_session(self._engine) as session:
            story = find_run(session, self._settings, run_id)
            spent = sum(
                agent.cost or 0.0
                for task in rows_of_run(session, story.id)
                for attempt in task.attempts
                for agent in attempt.agents
            )
            budget = story.budget
        notice(self._engine, root, run_id, self._lines, self._kill)
        return root, run_directory(root, run_id), budget is None or spent < budget

    def _plan_keys(self, root: Path, run_id: str) -> list[str]:
        try:
            plan = load_plan(root, run_id)
        except PlanFileError as exc:
            raise Conflict(str(exc)) from None
        return [str(task.get("jira_key") or task["id"]) for task in plan["tasks"]]

    def _check(
        self, root: Path, folder: Path, run_id: str, key: str, budget_left: bool
    ) -> tuple[int | None, str]:
        """(the attempt to go on with, the stage it resumes from), or Conflict: refused."""
        if task_states(root, run_id, self._engine).get(key) == MERGED:
            raise Conflict(f"{key} is already merged: it is done.")
        settled = control.settled(folder, key)
        if settled and settled.state == control.CANCELLED:
            raise Conflict(f"{key} was cancelled: that is final, it is not continued.")
        if control.pending(folder, key):
            raise Conflict(f"{key} is still being stopped: try again in a moment.")
        noted = continue_request.wanted(folder, key)
        if not settled and noted is None:
            running = loop_alive(folder, run_id, self._lines)
            raise Conflict(
                f"{key} is running now."
                if running
                else f"{key} is not stopped: nothing to continue."
            )
        if not budget_left:
            raise Conflict(f"The budget of run {run_id} is used up: raise it, then continue.")
        number = noted if noted is not None else (settled.attempt if settled else None)
        if number is None:
            return None, "builder"
        with get_session(self._engine) as session:
            found = merge_rows.newest_attempt(session, run_id, key)
        if found is None or found[1].number != number or found[1].outcome not in OPEN:
            state = found[1].outcome if found else "missing"
            raise Conflict(f"Attempt {number} of {key} is {state}: it cannot be continued.")
        try:
            resume_ready(self._settings, run_id, key, number)
        except BuildError as exc:
            raise Conflict(str(exc)) from None
        return number, checkpoint.resume_stage(root, run_id, key, number)

    def _go(self, ready: list, skipped: list[str], run_id: str, root: Path, folder: Path):
        for key, number, _ in ready:
            continue_request.release(folder, key, number)
        started = not loop_alive(folder, run_id, self._lines)
        if started:
            clear_stale_lock(folder, run_id, self._lines)  # a killed loop leaves its lock behind
            self._launch(folder, run_id, BRIGADE_FOLDER)
        where = ", ".join(f"{key} from {stage}" for key, _, stage in ready)
        return ContinueOut(
            run_id=run_id,
            continuing=[key for key, _, _ in ready],
            skipped=skipped,
            loop_started=started,
            detail=f"Continuing {where}." + (" A new loop was started." if started else ""),
        )
