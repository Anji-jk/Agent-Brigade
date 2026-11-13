import sys
import time

from pipeline.workspace import commands as c

PY = f'"{sys.executable}"'


def test_run_command_pass_fail_and_output(tmp_path):
    ok = c.run_command(f"{PY} -c \"print('hi')\"", tmp_path, timeout=30)
    assert ok.passed and ok.exit_code == 0 and "hi" in ok.output_tail
    bad = c.run_command(f'{PY} -c "import sys; sys.exit(3)"', tmp_path, timeout=30)
    assert not bad.passed and bad.exit_code == 3 and not bad.timed_out


def test_a_line_is_run_by_the_shell_so_cd_and_chains_work(tmp_path):
    (tmp_path / "frontend").mkdir()
    line = f'cd frontend && {PY} -c "import os; print(os.path.basename(os.getcwd()))"'
    result = c.run_command(line, tmp_path, timeout=30)
    assert result.passed and result.output_tail.strip() == "frontend"
    assert result.command == line


def test_error_output_is_kept_with_the_normal_output(tmp_path):
    code = "import sys; print('out'); print('oops', file=sys.stderr); sys.exit(1)"
    result = c.run_command(f'{PY} -c "{code}"', tmp_path, timeout=30)
    assert "out" in result.output_tail and "oops" in result.output_tail


def test_a_missing_program_shows_the_shells_own_message(tmp_path):
    result = c.run_command("no-such-program-xyz --version", tmp_path, timeout=30)
    assert not result.passed and result.exit_code != 0
    assert "no-such-program-xyz" in result.output_tail


def test_a_timeout_stops_the_whole_tree_and_returns(tmp_path):
    child = "import time; time.sleep(60)"
    start = f"subprocess.Popen([sys.executable, '-c', '{child}'])"
    parent = f"import subprocess, sys, time; {start}; time.sleep(60)"
    started = time.monotonic()
    result = c.run_command(f'{PY} -c "{parent}"', tmp_path, timeout=1)
    assert result.timed_out and result.exit_code is None and not result.passed
    assert time.monotonic() - started < 30  # not stuck waiting for the child's open pipe


def test_output_keeps_only_the_end(tmp_path):
    code = f"print('x' * {c.OUTPUT_TAIL_CHARS * 2}); print('END')"
    result = c.run_command(f'{PY} -c "{code}"', tmp_path, timeout=30)
    assert len(result.output_tail) == c.OUTPUT_TAIL_CHARS
    assert result.output_tail.rstrip().endswith("END")
