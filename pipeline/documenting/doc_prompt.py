"""The message the Documenter receives: its task, the files it may write, and the facts.

Every rule is in .claude/agents/documenter.md. This module only puts the task and the measured
facts of the run into one message, and the Reviewer's list when the Documenter is asked again.
"""

from typing import Any

from pipeline.documenting.facts_format import format_facts
from pipeline.documenting.facts_model import StoryFacts

MAX_TEXT = 4_000
MAX_FEEDBACK = 4_000


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n... (cut short)"


def _list(items: list[str], empty: str) -> list[str]:
    return [f"- {item}" for item in items] or [empty]


def documenter_prompt(task: dict[str, Any], facts: StoryFacts, feedback: str = "") -> str:
    """The first message of a Documenter session for the documentation `task`."""
    lines: list[str] = []
    if feedback.strip():
        lines += [
            "## Feedback from the Documentation Reviewer",
            "These claims have no support in the facts. Correct each to the facts, or remove it.",
            _cut(feedback, MAX_FEEDBACK),
            "",
        ]
    lines += [
        f"# {task.get('jira_key') or task['id']}: {task['title']}",
        "",
        "## What is asked",
        _cut(task["description"], MAX_TEXT) or "(no description)",
        "",
        "## Accept (every one must be true when you are done)",
        *_list(task["acceptance_criteria"], "- (none)"),
        "",
        "## Outcome",
        _cut(task["expected_outcome"], MAX_TEXT),
        "",
        "## Files you may write (no others)",
        *_list(task["files"], "- (none: write nothing and say so in your report)"),
        "",
        "## Measured facts of the run (the only source for numbers, results and file lists)",
        "```",
        format_facts(facts),
        "```",
    ]
    return "\n".join(lines)
