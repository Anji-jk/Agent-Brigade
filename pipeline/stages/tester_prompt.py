"""The message the Tester receives: the task's criteria, what the Builder changed, how tests run.

Every rule the Tester follows is in .claude/agents/tester.md. This module only puts the facts
into one message. The criteria are numbered from 1 because the Tester's answer refers to them
by number. How tests run is the plan's own lines, copied from the project's CLAUDE.md: Brigade
does not know any test framework by name.
"""

from typing import Any

MAX_REPORT = 4_000
SHOWN_FILES = 60


def _bullets(items: list[str], empty: str) -> list[str]:
    return [f"- {item}" for item in items] or [empty]


def check_lines(task: dict[str, Any], plan_commands: dict[str, Any]) -> list[str]:
    """The lines that run the project's tests: the task's Verify lines, then the project checks."""
    lines = [*task.get("verification", []), *plan_commands.get("project_checks", [])]
    return list(dict.fromkeys(line for line in lines if line.strip()))


def tester_prompt(
    task: dict[str, Any], plan_commands: dict[str, Any], changed: list[str], builder_report: str
) -> str:
    """The first message of a Tester session for `task` (an entry of the plan)."""
    criteria = [f"{n}. {text}" for n, text in enumerate(task["acceptance_criteria"], start=1)]
    shown = changed[:SHOWN_FILES]
    more = [f"- ... and {len(changed) - SHOWN_FILES} more"] if len(changed) > SHOWN_FILES else []
    report = (builder_report or "").strip()
    if len(report) > MAX_REPORT:
        report = report[:MAX_REPORT] + "\n... (cut short)"
    return "\n".join(
        [
            f"# {task.get('jira_key') or task['id']}: {task['title']}",
            "",
            "## Acceptance criteria (write tests for these; answer by number)",
            *(criteria or ["(none)"]),
            "",
            "## Outcome",
            (task.get("expected_outcome") or "").strip() or "(none)",
            "",
            "## Files the Builder changed",
            *_bullets(shown, "- (none)"),
            *more,
            "",
            "## The Builder's report",
            report or "(no report)",
            "",
            "## Commands that run this project's tests (run them exactly as written)",
            *_bullets(check_lines(task, plan_commands), "- (none listed)"),
        ]
    )
