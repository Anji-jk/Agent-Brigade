"""Run the Jira updates on their own thread, so a slow Jira never slows the build.

The loop calls update() and goes straight on: the state is copied, queued and sent in order by
one worker. Nothing is merged away, so each "attempt started" comment still gets written. If
Jira is so slow that the queue fills, the oldest updates are dropped (jira-mirror catches the
board up from the story report). At the end, close() waits a little for the last update and
then lets the run finish whatever Jira is doing.
"""

import copy
import threading
from collections import deque

from pipeline.jira_sync.hook import StorySync
from pipeline.stages.story_report import StoryResult

BACKLOG = 50
CLOSE_WAIT = 60.0  # seconds the end of a run waits for Jira


class BackgroundSync:
    def __init__(self, sync: StorySync, backlog: int = BACKLOG) -> None:
        self.sync = sync
        self.queue: deque[tuple[StoryResult, set[str], bool]] = deque(maxlen=backlog)
        self.wake = threading.Condition()
        self.closing = False
        self.thread = threading.Thread(target=self._work, name="jira-sync", daemon=True)
        self.thread.start()

    def update(self, result: StoryResult, running: set[str], finished: bool = False) -> None:
        """Queue the state as it is now; never waits for Jira."""
        snapshot = (copy.deepcopy(result), set(running), finished)
        with self.wake:
            self.queue.append(snapshot)
            self.wake.notify()

    def _work(self) -> None:
        while True:
            with self.wake:
                while not self.queue and not self.closing:
                    self.wake.wait()
                if not self.queue:
                    return
                result, running, finished = self.queue.popleft()
            self.sync.update(result, running, finished)  # never raises

    def close(self, timeout: float | None = None) -> None:
        """Let the worker send what is queued, for at most `timeout` seconds (CLOSE_WAIT)."""
        with self.wake:
            self.closing = True
            self.wake.notify()
        self.thread.join(CLOSE_WAIT if timeout is None else timeout)
