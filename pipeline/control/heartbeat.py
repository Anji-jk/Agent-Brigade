"""A loop that is running says so: it touches ``story.beat`` every few seconds.

The page reads a run's state many times a minute. Asking the operating system about the loop's
process each time is slow on Windows (starting PowerShell, about a second), so a fresh beat is
taken as "alive" with no look at the process. A beat that stopped (the loop was killed, or the
file was never made by an older loop) proves nothing: then the process is looked at, as before.
Only the page's display uses this; starting, stopping and killing always look at the process.
"""

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

BEAT_FILE = "story.beat"
EVERY = 5.0  # seconds between beats
FRESH = 20.0  # a beat younger than this means the loop is alive (a few missed beats are fine)


@contextmanager
def beating(run_dir: Path, every: float = EVERY) -> Iterator[None]:
    """Beat in the background while the block runs; the file is removed when it ends."""
    path = Path(run_dir) / BEAT_FILE
    stop = threading.Event()

    def beat() -> None:
        while True:
            try:
                path.write_text(str(time.time()), encoding="utf-8")
            except OSError:  # a missed beat is not worth stopping the loop for
                pass
            if stop.wait(every):
                return

    worker = threading.Thread(target=beat, name="story-beat", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2)
        path.unlink(missing_ok=True)


def fresh(run_dir: Path, seconds: float = FRESH, now: Callable[[], float] = time.time) -> bool:
    """Did the loop of this run beat less than `seconds` ago?"""
    try:
        return now() - (Path(run_dir) / BEAT_FILE).stat().st_mtime < seconds
    except OSError:
        return False
