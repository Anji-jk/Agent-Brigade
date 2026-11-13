"""How one Builder run is started: its limits, its tools and what it may run or touch.

The Builder is started in its attempt worktree, so its file tools reach only that folder. It may
run only the exact check lines the person approved (the plan's setup and project_checks, and the
task's own verification lines). It may never read or edit a .env file, and may never read
the project's .agent-brigade folder. How many turns, dollars and seconds it gets comes from the
task's size in profiles.toml, never from this file.
"""

from pathlib import Path, PurePath
from typing import Any

from pipeline.planning.profiles import profile_for, role_settings
from pipeline.runner.claude_runner import AgentRequest, path_rule, secret_rules

REPO_ROOT = Path(__file__).resolve().parents[2]  # the Agent-Brigade folder
AGENT = "builder"
AGENT_FILE = REPO_ROOT / ".claude" / "agents" / "builder.md"
# Claude Code's shell tool is Bash where it finds Git Bash and PowerShell on Windows without it;
# a tool that does not exist on the machine is dropped, so the Builder is given both.
# Edits inside the worktree pass without asking; anything else that would need approval (a file
# outside it, a command that is not an approved line) is denied. Allow rules for Edit and Write
# are ignored by Claude Code on Windows, so the mode does this job, not a rule.
PERMISSION_MODE = "acceptEdits"
TOOLS = ("Read", "Edit", "Write", "Glob", "Grep", "Bash", "PowerShell")


def allowed_commands(plan_commands: dict[str, Any], task: dict[str, Any]) -> tuple[str, ...]:
    """The lines the Builder may run: the check lines, each also as its `&&` parts.

    Claude Code may test each part of ``cd a && b`` against the rules, so the parts are listed
    too. Nothing is allowed that is not a line the person approved.
    """
    lines = [*plan_commands.get("project_checks", []), *task.get("verification", [])]
    rules: list[str] = []
    for line in lines:
        for rule in (line, *(part.strip() for part in line.split("&&"))):
            if rule and rule not in rules:
                rules.append(rule)
    return tuple(rules)


def deny_rules(worktree: PurePath, project_root: PurePath) -> tuple[str, ...]:
    """Never read a .env anywhere that matters, never edit one, never read .agent-brigade."""
    return (
        *secret_rules(REPO_ROOT, project_root, worktree),
        path_rule("Read", project_root, ".agent-brigade/**"),
        path_rule("Read", worktree, ".agent-brigade/**"),
        path_rule("Edit", worktree, "**/.env"),
        path_rule("Edit", worktree, "**/.env.*"),
        path_rule("Edit", worktree, ".agent-brigade/**"),
    )


def builder_request(
    task: dict[str, Any],
    plan_commands: dict[str, Any],
    prompt: str,
    worktree: Path,
    project_root: Path,
    session_id: str,
) -> AgentRequest:
    limits = role_settings(profile_for(task["complexity"]), "builder")
    return AgentRequest(
        agent=AGENT,
        prompt=prompt,
        cwd=worktree,
        session_id=session_id,
        resume=False,
        allowed_bash=allowed_commands(plan_commands, task),
        timeout=limits.timeout_seconds,
        tools=TOOLS,
        deny=deny_rules(worktree, project_root),
        permission_mode=PERMISSION_MODE,
        max_turns=limits.max_turns,
        max_budget_usd=limits.max_budget_usd,
        model=limits.model,
        effort=limits.effort,
        agent_file=AGENT_FILE,
    )
