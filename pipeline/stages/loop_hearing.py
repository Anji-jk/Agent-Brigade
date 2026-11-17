"""What the story loop does with a person's Stop and Cancel (the part of the loop that listens).

A running task is stopped by its own thread (pipeline.stages.interrupt) and arrives here as
TaskInterrupted. Here are the other ways a person's word reaches a task: it had not started, it
was settled by an earlier loop, or the request came just after the judge said Done.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from core.runs import run_directory
from pipeline.control import continue_request
from pipeline.control import task_control as control
from pipeline.stages.interrupt import settle_task, settle_waiting
from pipeline.stages.story_report import CANCELLED, PAUSED, WAITING, StoryResult


class Hearing:
    """Settles a person's word into the loop's `result`; `note` writes to the story's event log."""

    def __init__(
        self,
        engine: Engine,
        root: Path,
        run_id: str,
        result: StoryResult,
        note: Callable[..., Any],
    ) -> None:
        self.engine, self.root, self.run_id = engine, root, run_id
        self.run_dir = run_directory(root, run_id)
        self.result, self.note = result, note

    def interrupted(self, key: str, state: str, stage: str) -> None:
        """A person stopped or cancelled `key`: say so, and what Continue would do."""
        paused = state == control.STOPPED
        outcome = self.result.tasks[key]
        outcome.status = PAUSED if paused else CANCELLED
        outcome.detail = (
            f"stopped on request; Continue resumes from the {stage} stage"
            if paused
            else f"cancelled on request while at the {stage} stage"
        )
        self.note("task_paused" if paused else "task_cancelled", key=key, stage=stage)

    def heard(self, key: str) -> bool | None:
        """For a task no thread is working on: settle what a person asked of it.

        True: a waiting request was settled now (something happened). False: an earlier word is
        on disk, and it holds even in a loop started afterwards. None: nobody said anything."""
        asked = control.pending(self.run_dir, key)
        if asked:  # nothing runs for this task, so nothing needs killing
            state, stage = settle_waiting(self.engine, self.root, self.run_id, key, asked)
            self.interrupted(key, state, stage)
            return True
        settled = control.settled(self.run_dir, key)
        if settled:
            self.interrupted(key, settled.state, settled.stage or "builder")
            return False
        return None

    def late_request(self, key: str, number: int) -> bool:
        """A Cancel that arrived after the judge said Done and before the merge wins: nothing is
        merged. A Stop that arrives so late is too late: the task has finished. True: cancelled."""
        action = control.pending(self.run_dir, key)
        if action == control.CANCEL:
            settle_task(
                self.engine, self.root, self.run_id, key, control.CANCELLED, "judge", number,
                force=True,
            )  # fmt: skip
            self.interrupted(key, control.CANCELLED, "judge")
            return True
        if action:
            control.clear_request(self.run_dir, key)
        return False

    def released(self, key: str) -> bool:
        """Was the Stop taken back (Continue)? Then a task this loop holds as stopped is not any
        more: it is put back among the tasks that wait."""
        if control.settled(self.run_dir, key) or control.pending(self.run_dir, key):
            return False
        outcome = self.result.tasks[key]
        outcome.status, outcome.detail = WAITING, ""
        self.note("task_released", key=key)
        return True

    def continuing(self, key: str) -> int | None:
        """The attempt a person asked to continue, if there is one waiting to go on."""
        return continue_request.wanted(self.run_dir, key)

    def started_again(self, key: str, number: int) -> None:
        """The task is running again: the note has done its work."""
        continue_request.spent(self.run_dir, key)
        self.note("task_continued", key=key, attempt=number)
