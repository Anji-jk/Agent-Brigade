"""The message the Documentation Reviewer receives: the documents and the measured facts.

Every rule is in .claude/agents/doc-reviewer.md. Each document is shown with numbered lines so
that a claim can name its place, and the line counts are what the answer is checked against.
"""

from typing import Any

from pipeline.documenting.facts_format import format_facts
from pipeline.documenting.facts_model import StoryFacts

MAX_LINES = 400


def shown_lines(text: str) -> list[str]:
    return text.splitlines()[:MAX_LINES]


def line_counts(documents: dict[str, str]) -> dict[str, int]:
    """Each document's number of lines as the Reviewer is shown them."""
    return {name: len(shown_lines(text)) for name, text in documents.items()}


def _numbered(name: str, text: str) -> list[str]:
    lines = shown_lines(text)
    cut = len(text.splitlines()) > MAX_LINES
    body = [f"{number:>4}| {line}" for number, line in enumerate(lines, 1)]
    return [f"### {name} ({len(lines)} lines{', cut short' if cut else ''})", "```", *body, "```"]


def doc_review_prompt(task: dict[str, Any], facts: StoryFacts, documents: dict[str, str]) -> str:
    lines = [
        f"# Review the documentation of {task.get('jira_key') or task['id']}: {task['title']}",
        "",
        "## Acceptance criteria (judge each one, numbered from 1)",
        *[f"{n}. {text}" for n, text in enumerate(task["acceptance_criteria"], 1)],
        "",
        "## Measured facts of the run",
        "```",
        format_facts(facts),
        "```",
        "",
        "## The documents (the files the Documenter wrote)",
    ]
    for name, text in documents.items():
        lines += [*_numbered(name, text), ""]
    if not documents:
        lines.append("(the Documenter wrote no file)")
    return "\n".join(lines)