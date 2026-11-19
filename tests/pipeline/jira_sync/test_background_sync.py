"""The Jira updates run on their own thread: the loop never waits for Jira."""

import threading
import time

from pipeline.jira_sync.background import BackgroundSync
from pipeline.stages.story_report import MERGED, StoryResult, TaskOutcome


class SlowSync:
    """A sync whose update holds until the test lets it go."""

    def __init__(self, hold=True):
        self.gate = threading.Event()
        if not hold:
            self.gate.set()
        self.seen: list[tuple[dict, set, bool]] = []

    def update(self, result, running, finished=False):
        self.gate.wait(5)
        self.seen.append((result.statuses(), set(running), finished))
        return []


def result(status="waiting"):
    return StoryResult("RUN", {"SMT-62": TaskOutcome(status, 1, "")})


def test_update_returns_at_once_while_jira_is_slow():
    slow = SlowSync()
    background = BackgroundSync(slow)
    began = time.monotonic()
    for _ in range(5):
        background.update(result(), {"SMT-62"})
    assert time.monotonic() - began < 1.0
    slow.gate.set()
    background.close(5)


def test_every_update_is_sent_in_order():
    slow = SlowSync()
    background = BackgroundSync(slow)
    background.update(result("waiting"), {"SMT-62"})
    background.update(result(MERGED), set(), finished=True)
    slow.gate.set()
    background.close(5)
    assert [(s["SMT-62"], f) for s, _, f in slow.seen] == [("waiting", False), (MERGED, True)]


def test_the_state_is_copied_when_the_update_is_made():
    slow = SlowSync()
    background = BackgroundSync(slow)
    one = result("waiting")
    background.update(one, set())
    one.tasks["SMT-62"].status = MERGED  # the loop goes on changing its own record
    slow.gate.set()
    background.close(5)
    assert slow.seen[0][0]["SMT-62"] == "waiting"


def test_close_waits_for_the_last_update():
    slow = SlowSync(hold=False)
    background = BackgroundSync(slow)
    background.update(result(MERGED), set(), finished=True)
    background.close(5)
    assert len(slow.seen) == 1


def test_close_gives_up_after_its_time_and_the_run_ends_anyway():
    slow = SlowSync()  # never released
    background = BackgroundSync(slow)
    background.update(result(), set())
    began = time.monotonic()
    background.close(0.2)
    assert time.monotonic() - began < 2.0
    slow.gate.set()


def test_a_long_backlog_drops_the_oldest_updates():
    slow = SlowSync()
    background = BackgroundSync(slow, backlog=3)
    for n in range(10):
        background.update(result(), {f"T{n}"})
    slow.gate.set()
    background.close(5)
    assert {k for _, running, _ in slow.seen for k in running} >= {"T7", "T8", "T9"}
    assert len(slow.seen) <= 4  # the three kept, and the one already being sent
