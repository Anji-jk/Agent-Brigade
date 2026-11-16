"""How the Tester and the Reviewer are started: their limits, tools and what they may touch.

Both start in the attempt worktree, like the Builder, with their agent file passed by path.
The Tester may edit files (a test is a file) and run the approved check lines, so it works in
acceptEdits; what it wrote is measured afterwards. The Reviewer has Read, Grep and Glob only: it
cannot edit or run anything. Neither may read a .env file or the project's .agent-brigade folder.
How many turns, dollars and seconds each gets comes from profiles.toml, never from here.
"""

from pathlib import Path
from typing import Any

from pipeline.planning.profiles import profile_for, role_settings
from pipeline.runner.claude_runner import AgentRequest
from pipeline.stages.builder_session import (
    PERMISSION_MODE,
    REPO_ROOT,
    TOOLS,
    allowed_commands,
    deny_rules,
)

TESTER_FILE = REPO_ROOT / ".claude" / "agents" / "tester.md"
REVIEWER_FILE = REPO_ROOT / ".claude" / "agents" / "reviewer.md"
REVIEWER_TOOLS = ("Read", "Grep", "Glob")


def limits(task: dict[str, Any], role: str) -> dict[str, Any]:
    """The model, effort, turns and budget of `role` for this task's size."""
    chosen = role_settings(profile_for(task["complexity"]), role)
    return {
        "model": chosen.model,
        "effort": chosen.effort,
        "max_turns": chosen.max_turns,
        "max_budget_usd": chosen.max_budget_usd,
        "timeout_seconds": chosen.timeout_seconds,
    }


def tester_request(
    task: dict[str, Any],
    plan_commands: dict[str, Any],
    prompt: str,
    worktree: Path,
    project_root: Path,
    session_id: str,
    *,
    resume: bool = False,
    events_file: Path | None = None,
) -> AgentRequest:
    chosen = limits(task, "tester")
    return AgentRequest(
        agent="tester",
        prompt=prompt,
        cwd=worktree,
        session_id=session_id,
        resume=resume,
        allowed_bash=allowed_commands(plan_commands, task),
        timeout=chosen["timeout_seconds"],
        tools=TOOLS,
        deny=deny_rules(worktree, project_root),
        permission_mode=PERMISSION_MODE,
        max_turns=chosen["max_turns"],
        max_budget_usd=chosen["max_budget_usd"],
        model=chosen["model"],
        effort=chosen["effort"],
        agent_file=TESTER_FILE,
        events_file=events_file,
    )


def reviewer_request(
    task: dict[str, Any],
    prompt: str,
    worktree: Path,
    project_root: Path,
    session_id: str,
    *,
    resume: bool = False,
    events_file: Path | None = None,
) -> AgentRequest:
    chosen = limits(task, "reviewer")
    return AgentRequest(
        agent="reviewer",
        prompt=prompt,
        cwd=worktree,
        session_id=session_id,
        resume=resume,
        timeout=chosen["timeout_seconds"],
        tools=REVIEWER_TOOLS,
        deny=deny_rules(worktree, project_root),
        permission_mode="dontAsk",
        max_turns=chosen["max_turns"],
        max_budget_usd=chosen["max_budget_usd"],
        model=chosen["model"],
        effort=chosen["effort"],
        agent_file=REVIEWER_FILE,
        events_file=events_file,
    )
