"""The Planning use cases: Sync, the board tree, Check, Plan, Re-plan, Approve and the runs.

The planning itself is in pipeline.planning; this service adds what needs the database:
- every planning run is a story_runs row, named by its run id (SMT-56-20261112-a3f9);
- Plan and Re-plan answer at once and plan in the background (planning_jobs.py); the page asks
  for the run's status, so a reload loses nothing. One planning run per story at a time;
- Approve writes the plan's links to Jira. One approved run per story: approving another plan
  of the story marks the earlier approved one superseded, in its row and in its plan.json;
- a run left planning when Brigade stopped is marked failed at the next start (recover).
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.services.planning_jobs import JobContext, PlanningJob, run_job
from backend.services.planning_tree import TreeView, build_tree
from backend.services.planning_types import (
    STOPPED,
    Conflict,
    Executor,
    NotFound,
    PlanningServiceError,
    RunView,
    run_id_of,
)
from core.db import get_session
from core.db.models import StoryRun, TrackerItem
from core.db.repositories import story_runs as runs
from core.db.repositories.projects import sync_env_project
from core.db.repositories.tracker_items import board, last_synced
from core.runs import new_run_id, run_directory
from core.settings import Settings
from core.trackers.jira.client import JiraClient
from core.trackers.jira.story import check_story_key, read_story
from core.trackers.jira.sync import SyncResult, sync_board
from pipeline.planning.approval import ApprovalError, approve_plan, mark_superseded
from pipeline.planning.plan_file import PlanFileError, load_plan
from pipeline.planning.readiness import StoryCheck, run_checks
from pipeline.runner.claude_runner import AgentRunner
from pipeline.workspace.git import repository_root


class PlanningService:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        runner: AgentRunner,
        client_factory: Callable[[Settings], JiraClient] = JiraClient.from_settings,
        executor: Executor | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._client_factory = client_factory
        self._executor = executor or ThreadPoolExecutor(2, thread_name_prefix="planning")
        self._now = now
        self._context = JobContext(settings, engine, runner, client_factory, now)
        self._lock = threading.Lock()  # starting runs and approving: one decision at a time

    # ---------- start and stop ----------

    def recover(self) -> int:
        with get_session(self._engine) as session:
            return runs.fail_unfinished(session, STOPPED, self._now())

    def close(self) -> None:
        shutdown = getattr(self._executor, "shutdown", None)
        if shutdown:
            shutdown(wait=False, cancel_futures=True)

    # ---------- the board ----------

    def sync(self) -> SyncResult:
        client = self._client_factory(self._settings)
        try:
            with get_session(self._engine) as session:
                project_id = self._project_id(session)
                return sync_board(session, project_id, client, self._settings.jira_project_key)
        finally:
            client.close()

    def tree(self) -> TreeView:
        with get_session(self._engine) as session:
            project_id = self._project_id(session)
            return build_tree(
                self._settings.jira_project_key,
                board(session, project_id),
                runs.latest_runs(session, project_id),
                last_synced(session, project_id),
            )

    def checks(self, key: str, run_tests: bool = False) -> StoryCheck:
        """The checks before planning. The tests run only when asked: Plan runs them anyway."""
        key = check_story_key(key, self._settings.jira_project_key or None)
        client = self._client_factory(self._settings)
        try:
            story = read_story(client, key, self._settings.jira_project_key or None)
        finally:
            client.close()
        return run_checks(story, self._settings, run_tests=run_tests)

    def checks_context(self) -> tuple[str, str]:
        """The project folder (empty if none is set) and the base branch the checks look at."""
        folder = self._settings.project_path
        return (str(folder) if folder else "", self._settings.base_branch)

    # ---------- planning ----------

    def plan(self, key: str, budget: float | None) -> StoryRun:
        key = check_story_key(key, self._settings.jira_project_key or None)
        with self._lock, get_session(self._engine) as session:
            project_id = self._project_id(session)
            item = session.get(TrackerItem, key)
            if item is None or item.project_id != project_id or item.type != "story":
                raise NotFound(f"{key} is not a story on the board: Sync from Jira first.")
            row = self._start(session, project_id, key, budget)
        return self._submit(PlanningJob(project_id, key, run_id_of(row), budget))

    def replan(self, run_id: str, changes: str, budget: float | None) -> StoryRun:
        changes = (changes or "").strip()
        if not changes:
            raise PlanningServiceError("Say what should change: a re-plan needs your idea.")
        with self._lock, get_session(self._engine) as session:
            project_id = self._project_id(session)
            old = self._row(session, project_id, run_id)
            if old.status != runs.WAITING:
                hint = " Plan the story again instead." if old.status == runs.APPROVED else ""
                raise Conflict(
                    f"Run {run_id} is {old.status}: only a plan waiting for approval can be "
                    f"re-planned.{hint}"
                )
            budget = budget if budget is not None else old.budget
            row = self._start(session, project_id, old.story_key, budget)
        job = PlanningJob(project_id, row.story_key, run_id_of(row), budget, run_id, changes)
        return self._submit(job)

    def approve(self, run_id: str) -> RunView:
        with self._lock:
            with get_session(self._engine) as session:
                project_id = self._project_id(session)
                row = self._row(session, project_id, run_id)
                if row.status != runs.WAITING:
                    raise Conflict(
                        f"Run {run_id} is {row.status}: only a waiting plan can be approved."
                    )
                earlier = [
                    run_id_of(other)
                    for other in runs.runs_with_status(
                        session, project_id, row.story_key, runs.APPROVED
                    )
                ]
            root = repository_root(self._project_folder())
            client = self._client_factory(self._settings)
            try:
                approve_plan(root, run_id, client, self._settings.jira_project_key or None)
            finally:
                client.close()
            with get_session(self._engine) as session:
                self._row(session, project_id, run_id).status = runs.APPROVED
                for other in earlier:
                    self._replace_approved(session, project_id, root, other, run_id)
        return self.run(run_id)

    # ---------- reading runs ----------

    def run(self, run_id: str) -> RunView:
        with get_session(self._engine) as session:
            row = self._row(session, self._project_id(session), run_id)
        if not row.plan_file or row.status == runs.FAILED:
            return RunView(row, None)
        plan_file = Path(row.plan_file)
        try:
            return RunView(row, load_plan(plan_file.parents[3], run_id))
        except (PlanFileError, IndexError, ValueError) as exc:
            return RunView(row, None, f"The plan file could not be read: {exc}")

    def story_runs(self, key: str) -> list[StoryRun]:
        key = check_story_key(key, self._settings.jira_project_key or None)
        with get_session(self._engine) as session:
            return runs.runs_of_story(session, self._project_id(session), key)

    # ---------- helpers ----------

    def _project_id(self, session: Session) -> int:
        project = sync_env_project(session, self._settings)
        if project is None:
            raise PlanningServiceError("No project: BRIGADE_PROJECT_PATH is empty in .env.")
        return project.id

    def _project_folder(self) -> Path:
        folder = self._settings.project_path
        if folder is None:
            raise PlanningServiceError("No project: BRIGADE_PROJECT_PATH is empty in .env.")
        return folder

    def _row(self, session: Session, project_id: int, run_id: str) -> StoryRun:
        row = runs.get_run(session, project_id, run_id)
        if row is None:
            raise NotFound(f"Run {run_id} was not found in this project.")
        return row

    def _start(self, session: Session, project_id: int, key: str, budget: float | None) -> StoryRun:
        if runs.runs_with_status(session, project_id, key, runs.PLANNING):
            raise Conflict(f"{key} is already being planned: wait for that run to finish.")
        folder = self._settings.project_path

        def taken(candidate: str) -> bool:
            on_disk = folder is not None and run_directory(folder, candidate).exists()
            return on_disk or runs.run_id_taken(session, candidate)

        run_id = new_run_id(key, taken, self._now)
        return runs.start_run(session, project_id, key, run_id, budget, self._now())

    def _submit(self, job: PlanningJob) -> StoryRun:
        try:
            self._executor.submit(run_job, job, self._context)
        except RuntimeError as exc:  # the executor is shutting down
            with get_session(self._engine) as session:
                row = self._row(session, job.project_id, job.run_id)
                row.status, row.error, row.ended_at = runs.FAILED, str(exc), self._now()
        with get_session(self._engine) as session:
            return self._row(session, job.project_id, job.run_id)

    def _replace_approved(
        self, session: Session, project_id: int, root: Path, run_id: str, new_run_id: str
    ) -> None:
        """One approved run per story: the earlier one is kept, marked replaced."""
        try:
            mark_superseded(root, run_id, new_run_id, approved_too=True)
        except (ApprovalError, PlanFileError):
            pass  # the row is what Brigade builds from; a missing or odd file changes nothing
        self._row(session, project_id, run_id).status = runs.SUPERSEDED
