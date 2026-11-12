"""Run a project's own command, such as its tests. Ported from Agent Lab (checks.py).

The test command comes from BRIGADE_TEST_COMMAND. A leading `python` is replaced by the
project's own .venv Python when it has one, so the tests run with the project's packages, not
Brigade's.
"""

import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TEST_COMMAND = ("python", "-m", "pytest", "-q")
OUTPUT_TAIL_CHARS = 4000


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int | None  # None: it timed out or could not start
    timed_out: bool
    output_tail: str
    seconds: float

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def venv_python(root: Path) -> Path | None:
    """The project's .venv Python, on Windows or Linux, or None."""
    for candidate in (root / ".venv" / "Scripts" / "python.exe", root / ".venv" / "bin" / "python"):
        if candidate.is_file():
            return candidate
    return None


def project_python(root: Path) -> str:
    """The Python that runs the project's tests: its .venv, else the one running Brigade."""
    found = venv_python(root)
    return str(found) if found else sys.executable


def split_command(text: str) -> tuple[str, ...]:
    """A command line as words. Quotes group words, and Windows backslashes are kept."""
    words = shlex.split(text, posix=False)
    return tuple(
        word[1:-1] if len(word) > 1 and word[0] == word[-1] == '"' else word for word in words
    )


def project_test_command(root: Path, configured: str = "") -> tuple[str, ...]:
    """The command that runs the project's tests, with `python` made the project's Python."""
    command = split_command(configured) if configured.strip() else DEFAULT_TEST_COMMAND
    if command and command[0].lower() in ("python", "python3", "py"):
        command = (project_python(root), *command[1:])
    return command


def run_command(command: tuple[str, ...], cwd: Path, *, timeout: int) -> CommandResult:
    """Run a command to the end, keeping only the end of its output."""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else ""
        return CommandResult(command, None, True, partial[-OUTPUT_TAIL_CHARS:], _since(started))
    except OSError as exc:
        reason = f"Could not start {command[0]}: {type(exc).__name__}"
        return CommandResult(command, None, False, reason, _since(started))
    output = (completed.stdout or "") + (completed.stderr or "")
    return CommandResult(
        command, completed.returncode, False, output[-OUTPUT_TAIL_CHARS:], _since(started)
    )


def _since(started: float) -> float:
    return time.monotonic() - started
