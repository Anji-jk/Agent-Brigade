from pathlib import PureWindowsPath

from pipeline.stages import builder_session as s
from tests.pipeline.planning.test_plan_file import task


def test_only_approved_lines_and_their_parts_may_run():
    commands = {
        "setup": ["cd frontend && npm ci"],
        "project_checks": ["cd frontend && npx eslint ."],
    }
    one = task("T1", verification=["cd frontend && npm run build", "npx eslint ."])
    allowed = s.allowed_commands(commands, one)
    assert allowed == (
        "cd frontend && npx eslint .", "cd frontend", "npx eslint .",
        "cd frontend && npm run build", "npm run build",
    )  # fmt: skip
    assert "npm ci" not in allowed  # setup is run by Brigade, not by the Builder


def test_the_request_uses_the_worktree_limits_and_agent_file(tmp_path):
    work, root = tmp_path / "w", tmp_path / "p"
    one = task("T1", complexity="medium", jira_key="SMT-62")
    request = s.builder_request(one, {"project_checks": []}, "go", work, root, "sid")
    assert request.cwd == work and request.agent == "builder" and request.resume is False
    assert request.tools == ("Read", "Edit", "Write", "Glob", "Grep", "Bash", "PowerShell")
    assert (request.model, request.effort) == ("sonnet", "medium")
    assert request.max_turns == 25 and request.max_budget_usd == 1.8  # 60% of $3 / 25 turns
    assert request.agent_file == s.AGENT_FILE and s.AGENT_FILE.is_file()


def test_the_deny_rules_cover_env_files_and_brigade_state(tmp_path):
    rules = s.deny_rules(tmp_path / "w", tmp_path / "p")
    for needle in ("Read(", "Edit("):
        assert any(r.startswith(needle) for r in rules)
    assert any(r.endswith("/w/**/.env)") for r in rules if r.startswith("Read("))
    assert any(r.endswith("/p/**/.env)") for r in rules)
    assert any(r.startswith("Edit(") and r.endswith(".agent-brigade/**)") for r in rules)
    assert any(r.startswith("Read(") and r.endswith("/p/.agent-brigade/**)") for r in rules)


def test_on_windows_the_drive_becomes_a_folder_in_every_rule():
    rules = s.deny_rules(PureWindowsPath(r"C:\bw\run\SMT-62-1"), PureWindowsPath(r"C:\proj"))
    assert "Read(//c/bw/run/SMT-62-1/**/.env)" in rules
    assert "Edit(//c/bw/run/SMT-62-1/**/.env)" in rules
    assert "Read(//c/proj/.agent-brigade/**)" in rules


def test_the_builder_runs_in_accept_edits_mode(tmp_path):
    # an Edit/Write allow rule is ignored on Windows (Claude Code), so the mode allows the edits
    one = task("T1", complexity="medium", jira_key="SMT-62")
    request = s.builder_request(
        one, {"project_checks": []}, "go", tmp_path / "w", tmp_path / "p", "sid"
    )
    assert request.permission_mode == s.PERMISSION_MODE == "acceptEdits"
