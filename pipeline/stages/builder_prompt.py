"""The message the Builder receives: one sub-task of the plan, as data.

Every rule the Builder follows is in .claude/agents/builder.md. This module only puts the task
into one message: what must be true when it is done, the files it is expected to change, what
to read first, the commands that check it, and feedback from an earlier attempt. It gets no list
of the repository's files and no other sub-task's text.
"""

from typing import Any

MAX_TEXT = 4_000
MAX_FEEDBACK = 4_000


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n... (cut short)"


def _list(items: list[str], empty: str) -> list[str]:
    return [f"- {item}" for item in items] or [empty]


def builder_prompt(task: dict[str, Any], feedback: str = "") -> str:
    """The first message of a Builder session for `task` (an entry of the plan)."""
    context = task.get("context") or {}
    lines = []
    if feedback.strip():
        lines += [
            "## Feedback from the earlier attempt",
            "Fix this first, then check the whole task again.",
            _cut(feedback, MAX_FEEDBACK),
            "",
        ]
    lines += [
        f"# {task.get('jira_key') or task['id']}: {task['title']}",
        "",
        "## Description",
        _cut(task["description"], MAX_TEXT) or "(no description)",
        "",
        "## Accept (every one must be true when you are done)",
        *_list(task["acceptance_criteria"], "- (none)"),
        "",
        "## Outcome",
        _cut(task["expected_outcome"], MAX_TEXT),
        "",
        "## Files you are expected to change",
        *_list(task["files"], "- (the plan names none: say in your report which you changed)"),
        "",
        "## Read first",
        *_list(context.get("read_first") or [], "- (nothing named: start from the files above)"),
        "",
        "## Notes",
        _cut(context.get("notes") or "", MAX_TEXT) or "(none)",
        "",
        "## Commands that check this task (run them exactly as written)",
        *_list(task["verification"], "- (none listed)"),
    ]
    return "\n".join(lines)
