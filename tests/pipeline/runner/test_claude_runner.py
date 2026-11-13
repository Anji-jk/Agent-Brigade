import json
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath

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

    def __init__(
        self,
        stdout: str | bytes = "",
        stderr: str | bytes = "",
        returncode: int = 0,
        raises=None,
    ):
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.raises = raises
        self.calls = []
        self.settings = {}

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if "--settings" in command:
            settings_index = command.index("--settings")
            self.settings = json.loads(Path(command[settings_index + 1]).read_text())
        else:
            self.settings = {}
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


def test_the_publisher_still_gets_bash_only_and_no_deny_rules():
    run = FakeRun(stdout=answer())
    ClaudeCliRunner("claude", run).run(request())
    command = run.calls[0][0]
    assert command[command.index("--tools") + 1] == "Bash"
    assert "--add-dir" not in command and "--max-turns" not in command
    assert "deny" not in run.settings["permissions"]


def test_a_read_only_agent_gets_its_tools_folders_and_deny_rules():
    run = FakeRun(stdout=answer())
    planner = AgentRequest(
        agent="planner",
        prompt="Plan SMT-56",
        cwd=CWD,
        session_id="11111111-2222-3333-4444-555555555555",
        resume=False,
        tools=("Read", "Grep", "Glob"),
        add_dirs=(Path("/work/skill-matrix"),),
        deny=("Read(//work/skill-matrix/**/.env)",),
        max_turns=10,
    )
    ClaudeCliRunner("claude", run).run(planner)
    command = run.calls[0][0]
    assert command[command.index("--tools") + 1] == "Read,Grep,Glob"
    assert command[command.index("--add-dir") + 1] == str(Path("/work/skill-matrix"))
    assert command[command.index("--max-turns") + 1] == "10"
    assert run.settings["permissions"] == {
        "allow": [],
        "defaultMode": "dontAsk",
        "deny": ["Read(//work/skill-matrix/**/.env)"],
    }


def test_path_rules_use_two_slashes_and_the_windows_drive_as_a_folder():
    windows = PureWindowsPath("C:/Users/anji/Skill Matrix")
    assert runner_module.path_rule("Read", windows, "**/.env") == (
        "Read(//c/Users/anji/Skill Matrix/**/.env)"
    )
    assert runner_module.path_rule(
        "Read", PurePosixPath("/home/anji/sm/"), ".agent-brigade/**"
    ) == ("Read(//home/anji/sm/.agent-brigade/**)")


def test_secret_rules_cover_every_env_file_in_every_folder():
    rules = runner_module.secret_rules(PurePosixPath("/a"), PurePosixPath("/b"))
    assert rules == (
        "Read(//a/**/.env)",
        "Read(//a/**/.env.*)",
        "Read(//b/**/.env)",
        "Read(//b/**/.env.*)",
    )


def test_an_agents_header_is_read_from_its_file(tmp_path):
    folder = tmp_path / ".claude" / "agents"
    folder.mkdir(parents=True)
    (folder / "planner.md").write_text(
        "---\nname: planner\nmodel: opus\ndescription: a: b\n---\n\nmodel: not this\n", "utf-8"
    )
    (folder / "plain.md").write_text("No header here.\n", "utf-8")
    header = runner_module.agent_header(tmp_path, "planner")
    assert header == {"name": "planner", "model": "opus", "description": "a: b"}
    assert runner_module.agent_header(tmp_path, "plain") == {}


def test_the_real_planner_header_is_read_only_opus():
    header = runner_module.agent_header(Path(__file__).resolve().parents[3], "planner")
    assert header["model"] == "opus"
    assert header["tools"] == "Read, Grep, Glob"


def test_a_spending_cap_is_passed_to_claude_code():
    run = FakeRun(stdout=answer())
    capped = AgentRequest(**{**request().__dict__, "max_budget_usd": 2.5})
    ClaudeCliRunner("claude", run).run(capped)
    command = run.calls[0][0]
    assert command[command.index("--max-budget-usd") + 1] == "2.5000"
    ClaudeCliRunner("claude", run).run(request())
    assert "--max-budget-usd" not in run.calls[1][0]


def test_a_run_that_hit_its_turn_limit_says_which_limit_and_how_big():
    run = FakeRun(stdout=answer(is_error=True, subtype="error_max_turns", result=""))
    limited = AgentRequest(**{**request().__dict__, "max_turns": 100})
    with pytest.raises(AgentError, match=r"stopped: it reached its limit of 100 turns \(error_max"):
        ClaudeCliRunner("claude", run).run(limited)


def test_a_run_that_hit_its_spending_limit_says_so():
    run = FakeRun(stdout=answer(is_error=True, subtype="error_max_budget_usd", result=""))
    capped = AgentRequest(**{**request().__dict__, "max_budget_usd": 5.0})
    with pytest.raises(AgentError, match=r"it reached its spending limit of \$5.00"):
        ClaudeCliRunner("claude", run).run(capped)


def test_a_limit_stop_without_a_known_limit_still_reports_the_reason():
    run = FakeRun(stdout=answer(is_error=True, subtype="error_max_turns", result=""))
    with pytest.raises(AgentError, match="publisher agent stopped: error_max_turns"):
        ClaudeCliRunner("claude", run).run(request())


# ---------- model, effort, an agent file outside cwd, and usage (step 4.2) ----------


def test_model_effort_and_an_agents_file_reach_the_command():
    asked = request()
    asked = AgentRequest(**{**asked.__dict__, "model": "sonnet", "effort": "low"})
    command = runner_module.claude_command("claude", asked, Path("s.json"), Path("a.json"))
    assert command[command.index("--agents") + 1] == "a.json"
    assert command[command.index("--model") + 1] == "sonnet"
    assert command[command.index("--effort") + 1] == "low"
    plain = runner_module.claude_command("claude", request(), Path("s.json"))
    assert not {"--agents", "--model", "--effort"} & set(plain)


def test_an_agent_file_is_written_for_the_run_and_a_bad_one_is_an_agent_error(tmp_path):
    good = tmp_path / "builder.md"
    good.write_text("---\ndescription: B\n---\nDo it.\n", encoding="utf-8")
    seen = {}

    def run(command, **kwargs):
        seen["agents"] = json.loads(Path(command[command.index("--agents") + 1]).read_text())
        return subprocess.CompletedProcess(command, 0, b'{"result": "ok"}', b"")

    asked = AgentRequest(**{**request().__dict__, "agent": "builder", "agent_file": good})
    ClaudeCliRunner("claude", run).run(asked)
    assert seen["agents"] == {"builder": {"description": "B", "prompt": "Do it."}}
    bad = AgentRequest(**{**asked.__dict__, "agent_file": tmp_path / "missing.md"})
    with pytest.raises(AgentError, match="could not be read"):
        ClaudeCliRunner("claude", run).run(bad)


def test_usage_and_model_are_read_from_the_result():
    stdout = json.dumps(
        {
            "result": "done",
            "session_id": "s1",
            "total_cost_usd": 0.5,
            "num_turns": 3,
            "duration_ms": 4000,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 5,
            },
            "modelUsage": {"claude-sonnet-5": {}},
        }
    )
    reply = runner_module.parse_reply(stdout, "", 0, request())
    assert (reply.input_tokens, reply.output_tokens, reply.cache_tokens) == (10, 20, 35)
    assert reply.model_used == "claude-sonnet-5"
    bare = runner_module.parse_reply('{"result": "x"}', "", 0, request())
    assert (bare.input_tokens, bare.cache_tokens, bare.model_used) == (None, None, None)


def test_settings_allow_each_line_under_each_shell_and_deny_the_rest():
    from pipeline.runner.claude_runner import claude_settings

    permissions = claude_settings(
        ("npm run build",), ("Read(//c/x/.env)",), ("Bash", "PowerShell")
    )["permissions"]
    assert permissions["allow"] == ["Bash(npm run build)", "PowerShell(npm run build)"]
    assert permissions["deny"] == ["Read(//c/x/.env)"]
    assert permissions["defaultMode"] == "dontAsk"


def test_an_editing_agent_runs_in_accept_edits_mode_and_prompts_are_denied():
    from dataclasses import replace

    from pipeline.runner.claude_runner import claude_command

    plain = claude_command("claude", request(), Path("s.json"))
    assert plain[plain.index("--permission-mode") + 1] == "dontAsk"
    assert "--permission-prompts" not in plain  # the Publisher is unchanged
    edits = claude_command("claude", replace(request(), permission_mode="acceptEdits"), Path("s"))
    assert edits[edits.index("--permission-mode") + 1] == "acceptEdits"
    assert edits[edits.index("--permission-prompts") + 1] == "none"
