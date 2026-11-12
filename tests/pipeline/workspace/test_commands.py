import sys

import pytest

from pipeline.workspace import commands as c


def test_split_keeps_quoted_words_and_windows_paths():
    assert c.split_command('python -m pytest -q "tests\\unit tests"') == (
        "python",
        "-m",
        "pytest",
        "-q",
        "tests\\unit tests",
    )
    assert c.split_command(r"C:\venv\Scripts\python.exe -m pytest") == (
        r"C:\venv\Scripts\python.exe",
        "-m",
        "pytest",
    )


def test_default_command_uses_the_running_python_without_a_venv(tmp_path):
    assert c.project_test_command(tmp_path) == (sys.executable, "-m", "pytest", "-q")


@pytest.mark.parametrize("scripts", [("Scripts", "python.exe"), ("bin", "python")])
def test_python_becomes_the_projects_venv(tmp_path, scripts):
    venv = tmp_path / ".venv" / scripts[0]
    venv.mkdir(parents=True)
    (venv / scripts[1]).write_text("", encoding="utf-8")
    command = c.project_test_command(tmp_path, "python -m pytest backend -q")
    assert command == (str(venv / scripts[1]), "-m", "pytest", "backend", "-q")


def test_other_programs_are_kept(tmp_path):
    assert c.project_test_command(tmp_path, "npm test") == ("npm", "test")


def test_run_command_pass_fail_and_output(tmp_path):
    ok = c.run_command((sys.executable, "-c", "print('hi')"), tmp_path, timeout=30)
    assert ok.passed and ok.exit_code == 0 and "hi" in ok.output_tail
    bad = c.run_command((sys.executable, "-c", "import sys; sys.exit(3)"), tmp_path, timeout=30)
    assert not bad.passed and bad.exit_code == 3 and not bad.timed_out


def test_run_command_timeout(tmp_path):
    slow = (sys.executable, "-c", "import time; time.sleep(5)")
    result = c.run_command(slow, tmp_path, timeout=1)
    assert result.timed_out and result.exit_code is None and not result.passed


def test_run_command_that_cannot_start(tmp_path):
    result = c.run_command(("no-such-program-xyz",), tmp_path, timeout=5)
    assert result.exit_code is None and "Could not start no-such-program-xyz" in result.output_tail


def test_output_keeps_only_the_end(tmp_path):
    code = f"print('x' * {c.OUTPUT_TAIL_CHARS * 2}); print('END')"
    result = c.run_command((sys.executable, "-c", code), tmp_path, timeout=30)
    assert len(result.output_tail) == c.OUTPUT_TAIL_CHARS
    assert result.output_tail.rstrip().endswith("END")
