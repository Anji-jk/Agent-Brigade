import subprocess
from dataclasses import replace

from pipeline.runner import stop_watch as sw
from pipeline.runner.claude_runner import AgentError, AgentStopped, ClaudeCliRunner
from tests.pipeline.runner.test_stream_events import (
    INIT,
    RESULT,
    FakePopen,
    FakeProcess,
    lines,
    run,
)


class Waiting:
    """A process that does not end by itself; each wait() runs `on_wait` then times out."""

    def __init__(self, on_wait=lambda calls: None, ends_at=None):
        self.calls, self.on_wait, self.ends_at = 0, on_wait, ends_at

    def wait(self, timeout=None):
        self.calls += 1
        self.on_wait(self.calls)
        if self.ends_at and self.calls >= self.ends_at:
            return 0
        raise subprocess.TimeoutExpired("claude", timeout or 0)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 0.1
        return self.now


def test_without_a_stop_file_it_is_just_a_wait():
    assert sw.wait_for(Waiting(ends_at=1), 5, None) == (0, sw.DONE)
    assert sw.wait_for(Waiting(), 5, None) == (None, sw.TIMED_OUT)


def test_a_process_that_ends_by_itself_is_done(tmp_path):
    assert sw.wait_for(Waiting(ends_at=3), 5, tmp_path / "stop", poll=0.01) == (0, sw.DONE)


def test_the_stop_file_appearing_ends_the_wait_as_stopped(tmp_path):
    stop = tmp_path / "stop"
    process = Waiting(on_wait=lambda calls: stop.write_text("x") if calls == 2 else None)
    assert sw.wait_for(process, 30, stop, poll=0.01) == (None, sw.STOPPED)
    assert process.calls == 2  # noticed at the next look, not after the time limit


def test_the_time_limit_still_applies_while_watching(tmp_path):
    assert sw.wait_for(Waiting(), 1.0, tmp_path / "stop", poll=0.01, clock=Clock()) == (
        None,
        sw.TIMED_OUT,
    )


def test_a_stop_asked_before_the_start_means_the_agent_is_never_started(tmp_path):
    runner, popen, asked = run(tmp_path, FakeProcess(lines(INIT, RESULT)))
    stop = tmp_path / "stop"
    stop.write_text("x")
    try:
        runner.run(replace(asked, stop_file=stop))
    except AgentStopped as exc:
        assert "not started" in str(exc)
    else:
        raise AssertionError("it should have refused to start")
    assert popen.command is None and popen.killed == []


def test_a_stop_during_the_run_kills_the_agent_and_says_it_was_stopped(tmp_path):
    stop = tmp_path / "stop"
    process = FakeProcess(lines(INIT), hang=True)
    popen = FakePopen(process)
    runner = ClaudeCliRunner("claude", popen=popen, kill=popen.kill)
    process.wait = Waiting(on_wait=lambda calls: stop.write_text("x") if calls == 2 else None).wait
    asked = replace(run(tmp_path, process)[2], stop_file=stop)
    try:
        runner.run(asked)
    except AgentStopped as exc:
        assert "stopped on request" in str(exc) and isinstance(exc, AgentError)
    else:
        raise AssertionError("it should have been stopped")
    assert popen.killed == [process]


def test_a_stop_file_that_never_appears_changes_nothing(tmp_path):
    process = FakeProcess(lines(INIT, RESULT))
    runner, popen, asked = run(tmp_path, process)
    asked = replace(asked, stop_file=tmp_path / "never")
    assert runner.run(asked).text == "all done" and popen.killed == []


def test_a_real_process_is_killed_within_a_second_of_the_stop_file_appearing(tmp_path):
    import sys
    import threading
    import time

    from pipeline.workspace.commands import kill_tree

    stop = tmp_path / "stop"
    process = subprocess.Popen(  # noqa: S603 - a sleeping child of our own
        [sys.executable, "-c", "import time; time.sleep(60)"],
        **({} if sys.platform == "win32" else {"start_new_session": True}),
    )
    threading.Timer(0.3, stop.write_text, args=["x"]).start()
    started = time.monotonic()
    try:
        code, how = sw.wait_for(process, 30, stop, poll=0.1)
        kill_tree(process)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
    assert (code, how) == (None, sw.STOPPED)
    assert time.monotonic() - started < 5 and process.returncode != 0
