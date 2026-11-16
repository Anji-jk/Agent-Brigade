"""Looking at a process: what command it is running, if it is running at all.

A process id alone proves nothing: Windows and Linux hand an id to another program once its
process has ended. So whatever Brigade wants to do to a process, it first looks at the command
line and does it only if that is still the command Brigade started.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

CommandLine = Callable[[int], "str | None"]


def command_line(pid: int) -> str | None:
    """The process's command line, or None when no such process is running."""
    pid = int(pid)
    try:
        if sys.platform == "win32":
            query = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"
            done = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            return done.stdout.strip() or None
        if Path("/proc").is_dir():
            raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
            return (
                raw.replace(b"\0", b" ").decode(errors="replace").strip() or None
            )  # empty: zombie
        done = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False
        )
        return done.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None