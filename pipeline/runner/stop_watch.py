"""Wait for an agent process, but also watch for a person's request to stop it.

The loop that started an agent is the one that stops it, so nothing here needs a process id: a
request is a file (pipeline.control.task_control), and this looks for it about once a second.
"""

import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

POLL_SECONDS = 1.0
DONE, STOPPED, TIMED_OUT = "done", "stopped", "timed_out"


def wait_for(
    process: Any,
    timeout: float,
    stop_file: Path | None,
    poll: float = POLL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int | None, str]:
    """(the exit code, how it ended): done, stopped (the file appeared) or timed_out.

    The code is None unless the process ended by itself. With no `stop_file` this is exactly
    `process.wait(timeout)`.
    """
    if stop_file is None:
        try:
            return process.wait(timeout=timeout), DONE
        except subprocess.TimeoutExpired:
            return None, TIMED_OUT
    deadline = clock() + timeout
    while True:
        left = deadline - clock()
        if left <= 0:
            return None, TIMED_OUT
        try:
            return process.wait(timeout=min(poll, left)), DONE
        except subprocess.TimeoutExpired:
            if stop_file.exists():
                return None, STOPPED
