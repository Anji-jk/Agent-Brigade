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
