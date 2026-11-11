import json
import subprocess
from pathlib import Path

import pytest

from pipeline.runner import claude_runner as runner_module
from pipeline.runner.claude_runner import AgentError, AgentRequest, ClaudeCliRunner

CWD = Path("/repo")


def request(resume=False, prompt="Add a quiz"):
    return AgentRequest(
        agent="publisher",
        prompt=prompt,
        cwd=CWD,
        session_id="11111111-2222-3333-4444-555555555555",
        resume=resume,
        allowed_bash=("python -m pipeline.publisher.cli epics", "python -m x --key *"),
        timeout=30,
    )


class FakeRun:
    """Stands in for subprocess.run; remembers the call and the settings file it was given."""

    def __init__(self, stdout: str | bytes = "", stderr="", returncode=0, raises=None):
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.raises = raises
        self.calls = []
        self.settings = None

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        self.settings = json.loads(Path(command[command.index("--settings") + 1]).read_text())
        if self.raises:
            raise self.raises
        return self.result


def answer(**extra):
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Here is the proposal.",
            "session_id": "11111111-2222-3333-4444-555555555555",
            "total_cost_usd": 0.0123,
            "num_turns": 3,
            "duration_ms": 4567,
            **extra,
        }
    )


def test_new_session_runs_the_agent_with_only_the_allowed_commands():
    run = FakeRun(stdout=answer())
    reply = ClaudeCliRunner("claude", run).run(request())

    command, kwargs = run.calls[0]
    assert command[:4] == ["claude", "-p", "--agent", "publisher"]
    assert command[-2:] == ["--session-id", "11111111-2222-3333-4444-555555555555"]
    for flag in ("--strict-mcp-config", "--output-format", "--tools", "--setting-sources"):
        assert flag in command
    assert command[command.index("--tools") + 1] == "Bash"
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    assert command[command.index("--setting-sources") + 1] == "project"
    assert kwargs["input"] == b"Add a quiz" and "text" not in kwargs  # bytes keep \n as \n
    assert kwargs["cwd"] == CWD and kwargs["timeout"] == 30
    assert "Add a quiz" not in command  # the prompt goes through stdin, never the command line
    assert run.settings == {
        "permissions": {
            "allow": [
                "Bash(python -m pipeline.publisher.cli epics)",
                "Bash(python -m x --key *)",
            ],
            "defaultMode": "dontAsk",
        }
    }
    assert reply.text == "Here is the proposal." and reply.cost_usd == 0.0123
    assert reply.turns == 3 and reply.duration_ms == 4567


def test_line_breaks_reach_claude_unchanged_and_output_is_decoded():
    run = FakeRun(stdout=answer(result="Zoë: done").encode("utf-8"))
    reply = ClaudeCliRunner("claude", run).run(request(prompt="line one\nline two"))
    assert run.calls[0][1]["input"] == b"line one\nline two"
    assert reply.text == "Zo\u00eb: done"


def test_resume_continues_the_same_session():
    run = FakeRun(stdout=answer())
    ClaudeCliRunner("claude", run).run(request(resume=True))
    command = run.calls[0][0]
    assert command[-2:] == ["--resume", "11111111-2222-3333-4444-555555555555"]
    assert "--session-id" not in command


def test_an_error_result_is_reported():
    run = FakeRun(stdout=answer(is_error=True, subtype="error_during_execution", result="boom"))
    with pytest.raises(AgentError, match="publisher agent stopped: boom"):
        ClaudeCliRunner("claude", run).run(request())


def test_output_that_is_not_json_reports_the_end_of_stderr():
    run = FakeRun(stdout="", stderr="Invalid API key · Please run /login", returncode=1)
    with pytest.raises(AgentError, match="exited with code 1: Invalid API key"):
        ClaudeCliRunner("claude", run).run(request())


def test_timeout_is_reported():
    run = FakeRun(raises=subprocess.TimeoutExpired("claude", 30))
    with pytest.raises(AgentError, match="did not finish within 30 seconds"):
        ClaudeCliRunner("claude", run).run(request())


def test_claude_that_cannot_start_is_reported():
    run = FakeRun(raises=FileNotFoundError("no such file"))
    with pytest.raises(AgentError, match="could not be started"):
        ClaudeCliRunner("claude", run).run(request())


def test_missing_claude_is_reported(monkeypatch):
    monkeypatch.setattr(runner_module.shutil, "which", lambda _name: None)
    with pytest.raises(AgentError, match="claude --version"):
        ClaudeCliRunner(None, FakeRun()).run(request())
