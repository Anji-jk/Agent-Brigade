"""The loop over the whole story: build, merge and retry every task until none can move.

run_story   goes over the plan's tasks, again and again, and moves each one that can move:
            - a Done attempt that is not merged yet is merged;
            - a Failed one is retried, until it has used all its attempts (then Failed for good);
            - a task never built is started when its dependencies are merged;
            - a task whose dependency is Failed, Blocked or needs a person is Blocked;
            - an attempt that needs a person (Needs review, Builder error, left unfinished) is
              not retried: money is not spent on a problem that code cannot explain;
            - a task a person Stopped is skipped, and the tasks that depend on it keep waiting;
              a task a person Cancelled is final, and the tasks that depend on it are Blocked;
            - a task a person Continued goes on in the same attempt, from the stage it reached.
Tasks that may run together do: up to BRIGADE_MAX_PARALLEL at once. A task waits only when
a rule says so: its dependencies are not merged, it may touch the same files as a running
task, or it is not parallel-safe (then it runs alone, and nothing starts beside it).
Only the agent work (build, check, test, judge) runs in worker threads. Everything else, the
decisions, the merges and the event log, happens in this thread, one thing at a time, so two
tasks that finish together never merge together.
It stops when nothing runs and a whole pass moves nothing. Git is the truth for "merged", so
running it again resumes: merged tasks are skipped and cost nothing. One loop at a time per
run (a lock file). The story run's status is not touched here.
"""

from concurrent.futures import FIRST_COMPLETED, Executor, Future, ThreadPoolExecutor, wait
from pathlib import Path

from sqlalchemy import Engine

from core.db import get_session, init_db
from core.db.repositories import merge_rows
from core.runs import run_directory
from core.settings import Settings
from core.trackers.jira.client import JiraClient
from pipeline.control.heartbeat import beating
from pipeline.jira_sync.background import BackgroundSync
from pipeline.jira_sync.hook import make_sync
from pipeline.planning.plan_order import overlapping_tasks
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages import events
from pipeline.stages.attempt_log import AttemptLog
from pipeline.stages.errors import BuildError
from pipeline.stages.interrupt import TaskInterrupted
from pipeline.stages.loop_hearing import Hearing
from pipeline.stages.merge_run import merge_attempt
from pipeline.stages.prepare import approved_plan, project_root
from pipeline.stages.retry import next_attempt_number
from pipeline.stages.schedule import MERGED as IS_MERGED
from pipeline.stages.schedule import start_blockers, task_states
from pipeline.stages.story_report import (
    BLOCKED,
    CANCELLED,
    FAILED,
    MERGED,
    NEEDS_PERSON,
    PAUSED,
    StoryResult,
    TaskOutcome,
    write_story_report,
)
from pipeline.stages.story_report import (
    FILE as REPORT_FILE,
)
from pipeline.stages.task_run import run_task
from pipeline.workspace.lock import run_lock

STOPPED = (FAILED, NEEDS_PERSON, BLOCKED, CANCELLED)  # final: the tasks that need it are Blocked


def _key(task: dict) -> str:
    return task.get("jira_key") or task["id"]


def _newest(engine: Engine, run_id: str, key: str) -> tuple[int, str | None] | None:
    """(the number, the outcome) of the task's newest attempt, or None."""
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, run_id, key)
        return (found[1].number, found[1].outcome) if found else None


class _Loop:
    def __init__(
        self,
        settings: Settings,
        run_id: str,
        runner: AgentRunner,
        engine: Engine,
        jira: JiraClient | None = None,
    ):
        self.settings, self.run_id, self.runner, self.engine = settings, run_id, runner, engine
        self.root: Path = project_root(settings)
        self.run_dir = run_directory(self.root, run_id)
        self.plan = approved_plan(self.root, run_id)
        self.by_id = {t["id"]: t for t in self.plan["tasks"]}
        self.safe = {_key(t): bool(t["parallel_safe"]) for t in self.plan["tasks"]}
        self.result = StoryResult(run_id, {_key(t): TaskOutcome() for t in self.plan["tasks"]})
        self.hearing = Hearing(engine, self.root, run_id, self.result, self.note)
        self.limit = max(1, settings.max_parallel)
        self.running: dict[str, tuple[Future, int]] = {}  # key -> (its worker, attempt number)
        sync = make_sync(settings, self.run_dir, run_id, self.plan, engine, jira)
        self.sync = BackgroundSync(sync) if sync else None  # Jira never slows the loop

    def push(self, finished: bool = False) -> None:
        """Let Jira show where the build is (best effort: it never stops the build)."""
        if self.sync:
            self.sync.update(self.result, set(self.running), finished)

    def note(self, kind: str, **data) -> None:
        events.record(self.root, self.run_id, kind, **data)

    def stop(self, key: str, status: str, detail: str) -> None:
        self.result.tasks[key].status, self.result.tasks[key].detail = status, detail
        self.note("task_stopped", key=key, status=status, detail=detail)

    def merge(self, key: str, number: int) -> None:
        log = AttemptLog(self.root, self.run_id, key, number)
        log.emit("merge_started")
        try:
            merged = merge_attempt(self.settings, self.run_id, key, number, self.engine)
        except Exception as exc:  # noqa: BLE001 - a refused merge stops this task, not the story
            log.emit("merge_finished", merged=False, error=str(exc))
            self.stop(key, NEEDS_PERSON, f"merge refused: {exc}")
            return
        log.emit("merge_finished", merged=merged.merged, how=merged.kind)
        if merged.merged:
            self.result.tasks[key].status = MERGED
            self.note("task_merged", key=key, attempt=number, how=merged.kind)
        else:
            self.note("task_failed", key=key, attempt=number, reason="could not be merged")

    def can_start(self, task: dict, resume: bool = False) -> bool:
        """A free place, nothing it must not run beside, and its start rules met. A task that is
        continued has met them already: it holds its place among the running tasks."""
        if len(self.running) >= self.limit:
            return False
        if self.running and not (task["parallel_safe"] and all(self.safe[k] for k in self.running)):
            return False
        near = {_key(self.by_id[i]) for i in overlapping_tasks(self.plan["tasks"], task["id"])}
        if near & set(self.running):  # a task not in the database yet cannot be seen by Git
            return False
        if resume:
            return True
        return not start_blockers(self.root, self.plan, self.run_id, _key(task), self.engine)

    def start(self, pool: Executor, key: str, number: int, resume: bool = False) -> None:
        if resume:
            self.hearing.started_again(key, number)
        else:
            self.note("task_started", key=key, attempt=number)
        more = {"resume": True} if resume else {}
        future = pool.submit(
            run_task, self.settings, self.run_id, key, self.runner, number, self.engine, **more
        )
        self.running[key] = (future, number)
        self.result.tasks[key].attempts = number

    def finish(self, key: str, number: int, future: Future) -> None:
        try:
            done = future.result()
        except TaskInterrupted as exc:
            self.hearing.interrupted(key, exc.state, exc.stage, exc.reason)
            return
        except Exception as exc:  # noqa: BLE001 - one task's crash must not end the others
            self.stop(key, NEEDS_PERSON, f"{type(exc).__name__}: {exc}")
            return
        if done.ok:
            if self.hearing.late_request(key, number):
                return
            self.note("task_done", key=key, attempt=number)
            self.merge(key, number)
        else:
            self.note("task_failed", key=key, attempt=number, reason="judge: not done")

    def collect(self) -> None:
        """Wait until at least one running task has ended, then deal with every ended one."""
        ended, _ = wait([f for f, _ in self.running.values()], return_when=FIRST_COMPLETED)
        for key, (future, number) in list(self.running.items()):
            if future in ended:
                del self.running[key]
                self.finish(key, number, future)

    def blocked_by_dependency(self, task: dict, key: str) -> bool:
        """Block `key` when a task it depends on is final (failed, cancelled...). A task a person
        only Stopped is not final: what depends on it waits, as it does for any unmerged task."""
        for dependency in task["depends_on"]:
            name = _key(self.by_id[dependency])
            if self.result.tasks[name].status in STOPPED:
                self.stop(key, BLOCKED, f"{name} did not finish, and {key} depends on it")
                return True
        return False

    def retry_number(self, key: str, number: int, kind: str | None) -> int | None:
        """The number the last attempt had, or the one a retry would replace; None: the task
        stops here (it used its attempts, or its attempt needs a person) and has been told so."""
        if kind == "failed":
            try:
                return (
                    next_attempt_number(self.engine, self.run_id, key, self.settings.max_retries)
                    - 1
                )
            except BuildError as exc:
                self.stop(key, FAILED, str(exc))
                return None
        if kind != "new":
            self.stop(key, NEEDS_PERSON, f"attempt {number} is {kind or 'unfinished'}")
            return None
        return number

    def step(self, task: dict, states: dict[str, str], pool: Executor) -> bool:
        """Move one task if it can move. True: something happened."""
        key = _key(task)
        outcome = self.result.tasks[key]
        if outcome.status == PAUSED:
            self.hearing.released(key)
        if outcome.status in STOPPED or outcome.status == PAUSED or key in self.running:
            return False
        if states.get(key) == IS_MERGED:
            outcome.status, outcome.detail = MERGED, "already merged"
            return False
        said = self.hearing.heard(key)
        if said is not None:  # a person's word about this task, settled now or earlier
            return said
        newest = _newest(self.engine, self.run_id, key)
        if newest:
            outcome.attempts = newest[0]
        if self.blocked_by_dependency(task, key):
            return True
        number, kind = newest or (0, "new")
        if newest and self.hearing.continuing(key) == number:
            if not self.can_start(task, resume=True):
                return False
            self.start(pool, key, number, resume=True)
            return True
        if kind == "done":
            self.merge(key, number)
            return True
        number = self.retry_number(key, number, kind)
        if number is None:
            return True
        if not self.can_start(task):
            return False
        self.start(pool, key, number + 1)
        return True

    def run(self) -> StoryResult:
        self.note("story_started", tasks=len(self.plan["tasks"]), parallel=self.limit)
        with ThreadPoolExecutor(max_workers=self.limit) as pool:
            while True:
                moved = False
                for task in self.plan["tasks"]:
                    states = task_states(self.root, self.run_id, self.engine)
                    did = self.step(task, states, pool)
                    moved = did or moved
                    if did:
                        self.push()
                if self.running:
                    self.collect()
                    self.push()
                elif not moved:
                    break
        self.note("story_finished" if self.result.ok else "story_stopped", **self.result.statuses())
        self.push(finished=True)
        if self.sync:
            self.sync.close()  # waits a little for Jira, then lets the run end
        return self.result


def run_story(
    settings: Settings,
    run_id: str,
    runner: AgentRunner,
    engine: Engine | None = None,
    jira: JiraClient | None = None,
) -> StoryResult:
    """Run every task of the approved plan to merged, or as far as it can go."""
    engine = init_db(engine)
    root = project_root(settings)
    approved_plan(root, run_id)  # refuse early, before the lock folder is made
    folder = run_directory(root, run_id)
    with run_lock(folder), beating(folder):
        (run_directory(root, run_id) / REPORT_FILE).unlink(missing_ok=True)  # the old word is stale
        result = _Loop(settings, run_id, runner, engine, jira).run()
    write_story_report(root, result)
    return result
