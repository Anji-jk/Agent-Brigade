"""How the Documenter is started: its limits, its tools and what it may touch.

It starts in the attempt worktree with its agent file passed by path. It may edit files (the
documentation is a file) but has no shell, so it cannot run anything. Which files it wrote is
measured afterwards against the plan's list, because Claude Code cannot be told to write only
some files. The limits come from profiles.toml, never from here.
"""

from pathlib import Path
from typing import Any

from pipeline.documenting.doc_profiles import documentation_settings
from pipeline.runner.claude_runner import AgentRequest
from pipeline.stages.builder_session import PERMISSION_MODE, REPO_ROOT, deny_rules

DOCUMENTER_FILE = REPO_ROOT / ".claude" / "agents" / "documenter.md"
DOC_REVIEWER_FILE = REPO_ROOT / ".claude" / "agents" / "doc-reviewer.md"
DOCUMENTER_TOOLS = ("Read", "Edit", "Write", "Glob", "Grep")
DOC_REVIEWER_TOOLS = ("Read", "Grep", "Glob")


def documenter_request(
    prompt: str,
    worktree: Path,
    project_root: Path,
    session_id: str,
    *,
    resume: bool = False,
    events_file: Path | None = None,
) -> AgentRequest:
    chosen = documentation_settings("documenter")
    return AgentRequest(
        agent="documenter",
        prompt=prompt,
        cwd=worktree,
        session_id=session_id,
        resume=resume,
        timeout=chosen.timeout_seconds,
        tools=DOCUMENTER_TOOLS,
        deny=deny_rules(worktree, project_root),
        permission_mode=PERMISSION_MODE,
        max_turns=chosen.max_turns,
        max_budget_usd=chosen.max_budget_usd,
        model=chosen.model,
        effort=chosen.effort,
        agent_file=DOCUMENTER_FILE,
        events_file=events_file,
    )


def doc_reviewer_request(
    prompt: str,
    worktree: Path,
    project_root: Path,
    session_id: str,
    *,
    resume: bool = False,
    events_file: Path | None = None,
) -> AgentRequest:
    """The Reviewer can only read: no Edit, no Write, no shell."""
    chosen = documentation_settings("reviewer")
    return AgentRequest(
        agent="doc-reviewer",
        prompt=prompt,
        cwd=worktree,
        session_id=session_id,
        resume=resume,
        timeout=chosen.timeout_seconds,
        tools=DOC_REVIEWER_TOOLS,
        deny=deny_rules(worktree, project_root),
        permission_mode="dontAsk",
        max_turns=chosen.max_turns,
        max_budget_usd=chosen.max_budget_usd,
        model=chosen.model,
        effort=chosen.effort,
        agent_file=DOC_REVIEWER_FILE,
        events_file=events_file,
    )


def limits(role: str = "documenter") -> dict[str, Any]:
    chosen = documentation_settings(role)
    return {
        "model": chosen.model,
        "effort": chosen.effort,
        "max_turns": chosen.max_turns,
        "max_budget_usd": chosen.max_budget_usd,
        "timeout_seconds": chosen.timeout_seconds,
    }
