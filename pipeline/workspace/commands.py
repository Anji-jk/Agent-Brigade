"""Run one of a project's own commands, such as its tests. Ported from Agent Lab (checks.py).

Brigade never knows a project's commands itself: they are the lines of its approved plan, which
come from the project's CLAUDE.md and which the person approved. Each line runs through the
system shell (cmd.exe on Windows, sh elsewhere), so ``cd frontend && npm ci`` works as written
and the shell finds ``npm`` the way it does for the person. If the program is missing the shell
says so, and that message is what is shown.
"""

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

OUTPUT_TAIL_CHARS = 4000
_DRAIN_SECONDS = 5


@dataclass(frozen=True)
class CommandResult:
    command: str  # the line, as approved
    exit_code: int | None  # None: it timed out or could not start
    timed_out: bool
    output_tail: str
    seconds: float

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def run_command(line: str, cwd: Path, *, timeout: int) -> CommandResult:
    """Run a line to the end, keeping only the end of its output (errors included, in order)."""
    started = time.monotonic()
    own_group = {} if os.name == "nt" else {"start_new_session": True}
    try:
        process = subprocess.Popen(  # noqa: S602 - the line is the person's approved command
            line,
            shell=True,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **own_group,
        )
    except OSError as exc:
        return CommandResult(line, None, False, f"Could not start: {exc}", _since(started))
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        return CommandResult(line, None, True, _rest(process)[-OUTPUT_TAIL_CHARS:], _since(started))
    return CommandResult(
        line, process.returncode, False, output[-OUTPUT_TAIL_CHARS:], _since(started)
    )


def _kill_tree(process: subprocess.Popen[str]) -> None:
    """Stop the shell and everything it started, so nothing keeps running after a timeout."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _rest(process: subprocess.Popen[str]) -> str:
    try:
        return process.communicate(timeout=_DRAIN_SECONDS)[0] or ""
    except subprocess.TimeoutExpired:
        return ""


def _since(started: float) -> float:
    return time.monotonic() - started
