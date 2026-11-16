"""Stop or Cancel one task of a running story, or stop every running task.

The page only leaves a note (pipeline.control.task_control); the story loop, which started the
agents, acts on it: it kills the agent within a second and records the task as stopped or
cancelled. When there is no loop to act (it ended, or the task was already stopped) nothing is
running, so the note is settled here at once. No process id is used anywhere, so nothing can
ever kill a process that is not Brigade's own.

STOP    the task can be continued later, from the stage it had reached.
CANCEL  final: it is never continued, the tasks that depend on it are Blocked, and its worktree
        and branch are kept for a person to look at (Brigade never deletes a branch).
"""

from pathlib import Path

from sqlalchemy import Engine

from backend.schemas.run_control import StopAllOut, TaskControlOut
from backend.services.planning_types import Conflict, NotFound
from backend.services.run_lookup import find_run, project_root
from core.db import get_session
from core.db.repositories import merge_rows
from core.runs import run_directory
from core.settings import Settings
from pipeline.control import task_control as control
from pipeline.control.launch import loop_alive
from pipeline.control.processes import CommandLine, command_line
from pipeline.planning.plan_file import PlanFileError, load_plan
from pipeline.stages.attempt_log import attempt_dir
from pipeline.stages.interrupt import settle_waiting
from pipeline.stages.schedule import MERGED, task_states

IN_FLIGHT = (None, "built", "done")  # an attempt not judged yet, or Done and not merged yet


class TaskControlService:
    def __init__(
        self, settings: Settings, engine: Engine, lines: CommandLine = command_line
    ) -> None:
        self._settings, self._engine, self._lines = settings, engine, lines

    # ---------- what a person can do ----------

    def stop(self, run_id: str, key: str) -> TaskControlOut:
        root, folder = self._open(run_id, key)
        self._refuse_if_final(root, folder, run_id, key, "stop")
        if control.pending(folder, key):
            raise Conflict(f"{key} is already being {self._word(folder, key)}.")
        if not loop_alive(folder, run_id, self._lines):
            raise Conflict(f"{key} is not running: this run has no loop working now.")
        if not self._in_flight(root, run_id, key):
            raise Conflict(f"{key} is not running now, so there is nothing to stop.")
        control.ask(folder, key, control.STOP)
        return TaskControlOut(
            run_id=run_id,
            key=key,
            state="stopping",
            detail="Its agent is being stopped; Continue will go on from the stage it had reached.",
        )

    def cancel(self, run_id: str, key: str) -> TaskControlOut:
        root, folder = self._open(run_id, key)
        self._refuse_if_final(root, folder, run_id, key, "cancel")
        if control.pending(folder, key) == control.CANCEL:
            raise Conflict(f"{key} is already being cancelled.")
        settled = control.settled(folder, key)
        if loop_alive(folder, run_id, self._lines) and not settled:
            control.ask(folder, key, control.CANCEL)  # the loop kills the agent and records it
            return TaskControlOut(
                run_id=run_id,
                key=key,
                state="cancelling",
                detail="Cancelling: its agent is stopped and its work is kept in Git.",
            )
        _, stage = settle_waiting(self._engine, root, run_id, key, control.CANCEL)
        return TaskControlOut(
            run_id=run_id,
            key=key,
            state="cancelled",
            detail=f"Cancelled at the {stage} stage. Its worktree and branch are kept.",
        )

    def stop_all(self, run_id: str) -> StopAllOut:
        root = project_root(self._settings)
        with get_session(self._engine) as session:
            find_run(session, self._settings, run_id)
        folder = run_directory(root, run_id)
        keys = self._plan_keys(root, run_id)
        running = [
            key
            for key in keys
            if loop_alive(folder, run_id, self._lines)
            and not control.pending(folder, key)
            and not control.settled(folder, key)
            and self._in_flight(root, run_id, key)
        ]
        if not running:
            raise Conflict(f"Run {run_id} has no running task to stop.")
        for key in running:
            control.ask(folder, key, control.STOP)
        return StopAllOut(run_id=run_id, stopping=running)

    # ---------- helpers ----------

    def _open(self, run_id: str, key: str) -> tuple[Path, Path]:
        root = project_root(self._settings)
        with get_session(self._engine) as session:
            find_run(session, self._settings, run_id)
        if key not in self._plan_keys(root, run_id):
            raise NotFound(f"Run {run_id} has no task {key}.")
        return root, run_directory(root, run_id)

    def _plan_keys(self, root: Path, run_id: str) -> list[str]:
        try:
            plan = load_plan(root, run_id)
        except PlanFileError as exc:
            raise Conflict(str(exc)) from None
        return [str(task.get("jira_key") or task["id"]) for task in plan["tasks"]]

    def _refuse_if_final(self, root: Path, folder: Path, run_id: str, key: str, what: str) -> None:
        if task_states(root, run_id, self._engine).get(key) == MERGED:
            raise Conflict(f"{key} is already merged: it is done, there is nothing to {what}.")
        settled = control.settled(folder, key)
        if settled and settled.state == control.CANCELLED:
            raise Conflict(f"{key} was cancelled: that is final.")
        if settled and what == "stop":
            raise Conflict(f"{key} is already stopped: continue it, or cancel it.")

    def _in_flight(self, root: Path, run_id: str, key: str) -> bool:
        """Is a thread of the loop working on this task? Its newest attempt is not judged yet, or
        a new attempt has begun its folder and not yet its row (the worktree is being made)."""
        with get_session(self._engine) as session:
            found = merge_rows.newest_attempt(session, run_id, key)
        if found is not None and found[1].outcome in IN_FLIGHT:
            return True
        next_number = found[1].number + 1 if found else 1
        return attempt_dir(root, run_id, key, next_number).is_dir()

    def _word(self, folder: Path, key: str) -> str:
        return "stopped" if control.pending(folder, key) == control.STOP else "cancelled"