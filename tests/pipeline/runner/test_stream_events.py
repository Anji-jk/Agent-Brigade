"""An agent run that keeps its event stream: every line as it arrives, with its time."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from pipeline.runner.claude_runner import AgentError, AgentRequest, ClaudeCliRunner

CWD = Path("/repo")
SESSION = "11111111-2222-3333-4444-555555555555"
INIT = {"type": "system", "subtype": "init", "model": "claude-sonnet-5-5"}
READ = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}}
RESULT = {
    "type": "result", "subtype": "success", "is_error": False, "result": "all done",
    "session_id": SESSION, "total_cost_usd": 0.12, "num_turns": 3, "duration_ms": 900,
    "usage": {"input_tokens": 10, "output_tokens": 5},
}  # fmt: skip


def lines(*events):
    return [(json.dumps(event) + "\n").encode() for event in events]


class FakeProcess:
    """Stands in for subprocess.Popen: its stdout is the stream, its stdin remembers the prompt."""

    def __init__(self, stdout, stderr=b"", returncode=0, hang=False):
        self.stdout, self.stderr = io.BytesIO(b"".join(stdout)), io.BytesIO(stderr)
        self.stdin = io.BytesIO()
        self.stdin.close = lambda: None  # keep the written prompt readable
        self.returncode, self.hang, self.pid = returncode, hang, 4242

    def wait(self, timeout=None):
        if self.hang:
            raise subprocess.TimeoutExpired("claude", timeout or 0)
        return self.returncode


class FakePopen:
    def __init__(self, process):
        self.process, self.command, self.kwargs, self.killed = process, None, None, []

    def __call__(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        return self.process

    def kill(self, process):
        self.killed.append(process)


def run(tmp_path, process, *, resume=False, name="builder.events.jsonl"):
    popen = FakePopen(process)
    runner = ClaudeCliRunner("claude", popen=popen, kill=popen.kill)
    asked = AgentRequest(
        agent="builder", prompt="Do it", cwd=CWD, session_id=SESSION, resume=resume,
        events_file=tmp_path / "attempts" / "SMT-62-1" / name, timeout=30,
    )  # fmt: skip
    return runner, popen, asked


def events_path(asked):
    assert asked.events_file is not None
    return asked.events_file


def test_the_stream_is_asked_for_and_the_prompt_is_sent_on_stdin(tmp_path):
    process = FakeProcess(lines(INIT, RESULT))
    runner, popen, asked = run(tmp_path, process)
    runner.run(asked)
    command = popen.command
    assert command is not None
    assert command[command.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in command
    assert process.stdin.getvalue() == b"Do it"


def test_every_event_is_kept_as_it_arrived_with_one_time_per_line(tmp_path):
    runner, _, asked = run(tmp_path, FakeProcess(lines(INIT, READ, RESULT)))
    runner.run(asked)
    kept = events_path(asked).read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["type"] for x in kept] == ["system", "assistant", "result"]
    assert asked.events_file is not None
    times = asked.events_file.with_suffix(".times").read_text(encoding="utf-8").splitlines()
    assert len(times) == 3 and all(t.endswith("+00:00") for t in times)


def test_the_answer_is_read_from_the_result_event(tmp_path):
    runner, _, asked = run(tmp_path, FakeProcess(lines(INIT, READ, RESULT)))
    reply = runner.run(asked)
    assert reply.text == "all done" and reply.cost_usd == 0.12 and reply.turns == 3


def test_a_resumed_run_adds_to_the_same_file(tmp_path):
    runner, _, asked = run(tmp_path, FakeProcess(lines(INIT, RESULT)))
    runner.run(asked)
    assert asked.events_file is not None
    again, _, second = run(tmp_path, FakeProcess(lines(READ, RESULT)), resume=True)
    again.run(second)
    assert len(asked.events_file.read_text(encoding="utf-8").splitlines()) == 4


def test_a_stream_with_no_result_event_reports_the_exit_code_and_stderr(tmp_path):
    runner, _, asked = run(tmp_path, FakeProcess(lines(INIT), stderr=b"it fell over", returncode=1))
    with pytest.raises(AgentError, match="exited with code 1: it fell over"):
        runner.run(asked)
    assert asked.events_file is not None
    assert asked.events_file.is_file()  # what was seen before it stopped is kept


def test_an_error_result_is_reported_as_before(tmp_path):
    bad = {**RESULT, "is_error": True, "subtype": "error_max_turns"}
    runner, _, asked = run(tmp_path, FakeProcess(lines(INIT, bad)))
    with pytest.raises(AgentError, match="builder agent stopped"):
        runner.run(asked)


def test_a_run_that_does_not_finish_in_time_is_stopped_and_reported(tmp_path):
    process = FakeProcess(lines(INIT), hang=True)
    runner, popen, asked = run(tmp_path, process)
    with pytest.raises(AgentError, match="did not finish within 30 seconds"):
        runner.run(asked)
    assert popen.killed == [process]
    assert asked.events_file is not None
    assert asked.events_file.is_file()


def test_a_run_without_an_events_file_is_unchanged(tmp_path):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess([], 0, json.dumps(RESULT), "")

    asked = AgentRequest(agent="builder", prompt="x", cwd=CWD, session_id=SESSION, resume=False)
    ClaudeCliRunner("claude", run=fake_run).run(asked)
    assert seen["command"][seen["command"].index("--output-format") + 1] == "json"
    assert "--verbose" not in seen["command"]
