"""Looking at a process: what command it is running, if it is running at all.

A process id alone proves nothing: Windows and Linux hand an id to another program once its
process has ended. So whatever Brigade wants to do to a process, it first looks at the command
line and does it only if that is still the command Brigade started.
"""

import platform
import subprocess
from collections.abc import Callable
from pathlib import Path

CommandLine = Callable[[int], "str | None"]


_UNKNOWN = object()  # psutil could not say (not installed, or not allowed to look)


def _by_psutil(pid: int) -> "str | None | object":
    """The command line through psutil: a few milliseconds, where starting PowerShell costs
    about a second on Windows. None when no such process runs; _UNKNOWN when psutil cannot say."""
    try:
        import psutil
    except ImportError:
        return _UNKNOWN
    try:
        return " ".join(psutil.Process(pid).cmdline()).strip() or None
    except psutil.NoSuchProcess:
        return None
    except (psutil.AccessDenied, psutil.Error):
        return _UNKNOWN


def _windows_command_line(pid: int) -> str | None:
    quick = _by_psutil(pid)
    if quick is not _UNKNOWN:
        return quick  # type: ignore[return-value]
    query = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"
    done = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return done.stdout.strip() or None


def _posix_command_line(pid: int) -> str | None:
    if Path("/proc").is_dir():
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode(errors="replace").strip() or None  # empty: zombie
    done = subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() or None


def command_line(pid: int) -> str | None:
    """The process's command line, or None when no such process is running."""
    pid = int(pid)
    # platform.system(), not sys.platform: Pylance treats the other platform's code as unreachable.
    look = _windows_command_line if platform.system() == "Windows" else _posix_command_line
    try:
        return look(pid)
    except (OSError, subprocess.SubprocessError):
        return None
