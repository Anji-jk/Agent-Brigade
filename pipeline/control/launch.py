"""Start the story loop as its own process, and tell later whether that process is still ours.

The loop must not live inside the web server: closing or restarting the server would kill a
story that is spending money. So Start launches ``python -m pipeline.stages loop <run_id>`` as a
detached process, writes its process id to ``launch.json`` in the run's folder, and sends its
output to ``loop.log`` beside it.

Whether a loop is running is answered by looking at the process, never by a saved status, which
nobody could update when the process dies: a process id counts only while its command line is
still the loop's. Two places name a candidate process: ``launch.json`` (started from the page)
and ``story.lock`` (also made by a loop started by hand in a terminal).
"""

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import utc_now
from pipeline.control.processes import CommandLine, command_line

LAUNCH_FILE = "launch.json"
LOG_FILE = "loop.log"
LOCK_FILE = "story.lock"
MODULE = "pipeline.stages"
LOOP_COMMANDS = ("loop", "story")  # `story` is what a person types in a terminal


@dataclass(frozen=True)
class Launch:
    pid: int
    command: list[str]
    started_at: str


def write_launch(run_dir: Path, launch: Launch) -> None:
    write_json_atomic(Path(run_dir) / LAUNCH_FILE, asdict(launch))


def read_launch(run_dir: Path) -> Launch | None:
    """The record, or None when there is none or it is damaged (a crash can leave half a file)."""
    try:
        data = json.loads((Path(run_dir) / LAUNCH_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pid = data.get("pid") if isinstance(data, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool):
        return None
    command = data.get("command")
    return Launch(
        pid,
        [str(part) for part in command] if isinstance(command, list) else [],
        str(data.get("started_at") or ""),
    )


def loop_command(run_id: str, python: str = sys.executable) -> list[str]:
    return [python, "-m", MODULE, "loop", run_id]


def is_loop_process(line: str | None, run_id: str) -> bool:
    """Is this command line the story loop of this run? Whole words only, so that the run
    SMT-61-20261113-6b1a is not mistaken for SMT-61-20261113-6b1a-2."""
    if not line:
        return False
    words = [word.strip("\"'") for word in line.split()]
    return MODULE in words and run_id in words and any(w in words for w in LOOP_COMMANDS)


def _lock_pid(run_dir: Path) -> int | None:
    try:
        return int((Path(run_dir) / LOCK_FILE).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def loop_alive(run_dir: Path, run_id: str, get_command_line: CommandLine = command_line) -> bool:
    launch = read_launch(run_dir)
    candidates = [launch.pid if launch else None, _lock_pid(run_dir)]
    return any(
        pid is not None and is_loop_process(get_command_line(pid), run_id) for pid in candidates
    )


def spawn_detached(
    command: list[str],
    cwd: Path,
    log: Path,
    popen: Callable[..., Any] = subprocess.Popen,
) -> Any:
    """Start `command` so that it survives this process; its output is appended to `log`."""
    log.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {"stdin": subprocess.DEVNULL, "cwd": cwd, "close_fds": True}
    if sys.platform == "win32":
        options["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
    else:
        options["start_new_session"] = True
    with log.open("ab") as out:
        return popen(command, stdout=out, stderr=subprocess.STDOUT, **options)


def launch_loop(
    run_dir: Path,
    run_id: str,
    repository: Path,
    python: str = sys.executable,
    popen: Callable[..., Any] = subprocess.Popen,
) -> Launch:
    """Start the loop of `run_id` from the Agent-Brigade folder `repository` and record it."""
    command = loop_command(run_id, python)
    process = spawn_detached(command, repository, Path(run_dir) / LOG_FILE, popen)
    launch = Launch(process.pid, command, utc_now())
    write_launch(run_dir, launch)
    return launch