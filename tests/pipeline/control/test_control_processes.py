import os
import subprocess
import sys

from pipeline.control.processes import command_line


def test_the_command_line_of_a_running_process_is_found():
    line = command_line(os.getpid())
    assert line is not None and "python" in line.lower()


def test_a_process_that_has_ended_has_no_command_line():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert command_line(child.pid) is None


def test_psutil_reads_the_command_line_of_a_running_process_and_none_of_a_gone_one():
    import os

    from pipeline.control import processes

    mine = processes._by_psutil(os.getpid())
    assert isinstance(mine, str) and mine  # some text: what this test run was started with
    assert processes._by_psutil(2**22 + 12345) is None  # no such process


def test_when_psutil_may_not_look_it_says_unknown_instead_of_gone(monkeypatch):
    import psutil

    from pipeline.control import processes

    def refuse(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(psutil, "Process", refuse)
    assert processes._by_psutil(4) is processes._UNKNOWN


def test_on_windows_the_quick_way_is_used_and_powershell_is_not_started(monkeypatch):
    import psutil

    from pipeline.control import processes

    class Fake:
        def __init__(self, pid):
            pass

        def cmdline(self):
            return ["python", "-m", "pipeline.stages", "loop", "SMT-1-x"]

    def no_shell(*args, **kwargs):
        raise AssertionError("PowerShell must not be started")

    monkeypatch.setattr(processes.platform, "system", lambda: "Windows")
    monkeypatch.setattr(psutil, "Process", Fake)
    monkeypatch.setattr(processes.subprocess, "run", no_shell)
    assert processes.command_line(5) == "python -m pipeline.stages loop SMT-1-x"


def test_on_windows_powershell_is_the_fallback_when_psutil_cannot_say(monkeypatch):
    from pipeline.control import processes

    class Done:
        stdout = "from powershell\n"

    monkeypatch.setattr(processes.platform, "system", lambda: "Windows")
    monkeypatch.setattr(processes, "_by_psutil", lambda pid: processes._UNKNOWN)
    monkeypatch.setattr(processes.subprocess, "run", lambda *a, **k: Done())
    assert processes.command_line(5) == "from powershell"
