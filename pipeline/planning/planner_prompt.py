"""The message the Planner receives: the story and the project, as data.

Every rule the Planner follows is in .claude/agents/planner.md. This module only puts facts
into one message: where the project is, the story, its sub-tasks with their Jira links, and
the tracked file list. For a re-plan it also holds the previous plan and the changes a person
asked for. The Planner gets no Jira tool and no credentials, only this text.
"""

import json
from pathlib import Path
from typing import Any

from core.trackers.models import Story, WorkItem

MAX_STORY_CHARS = 12_000
MAX_ITEM_CHARS = 4_000
MAX_FILES_CHARS = 8_000
MAX_PREVIOUS_CHARS = 16_000
MAX_CHANGES_CHARS = 4_000
SYSTEM_MARKER = "[Message from the Brigade system]"
PLAN_FIELDS = (
    "files",
    "complexity",
    "parallel_safe",
    "expected_outcome",
    "verification",
    "doc_target",
    "context",
)


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip() or "(no description)"
    return text if len(text) <= limit else text[:limit] + "\n... (cut short)"


def _subtask(item: WorkItem) -> str:
    labels = ", ".join(item.labels) or "none"
    return "\n".join(
        [
            f"### {item.key}  {item.summary}",
            f"Status: {item.status} | Priority: {item.priority or 'none'} | Labels: {labels}",
            f"Blocked by in Jira: {', '.join(item.blocked_by) or 'nothing'}",
            "",
            _cut(item.description, MAX_ITEM_CHARS),
        ]
    )


def _clean(text: str) -> str:
    """A person's text without lines that imitate Brigade's own markers."""
    lines = [
        line
        for line in text.strip().splitlines()
        if not line.lstrip().startswith((SYSTEM_MARKER, "--- BEGIN", "--- END"))
    ]
    return _cut("\n".join(lines), MAX_CHANGES_CHARS)


def _previous_plan(record: dict[str, Any]) -> str:
    """The earlier plan with sub-task keys instead of T1, T2: the Planner's own vocabulary."""
    keys = {task["id"]: task["jira_key"] for task in record["tasks"]}
    tasks = [
        {
            "key": task["jira_key"],
            "depends_on": [keys[blocker] for blocker in task["depends_on"]],
            "dependency_reasons": {
                keys[blocker]: reason for blocker, reason in task["dependency_reasons"].items()
            },
            **{name: task.get(name) for name in PLAN_FIELDS},
        }
        for task in record["tasks"]
    ]
    text = json.dumps(
        {
            "summary": record.get("summary", ""),
            "commands": record.get("commands") or {"setup": [], "project_checks": []},
            "tasks": tasks,
        },
        indent=1,
    )
    return text if len(text) <= MAX_PREVIOUS_CHARS else text[:MAX_PREVIOUS_CHARS] + "\n... (cut)"


def _money(budget: float | None) -> str:
    if budget is None:
        return "none set"
    return f"${budget:g} for planning and building this story together"


def planner_prompt(
    story: Story,
    *,
    project_root: Path,
    base_branch: str,
    docs_dir: str,
    files: str,
    budget: float | None = None,
    previous: dict[str, Any] | None = None,
    changes: str | None = None,
) -> str:
    """The whole first message for one planning run (a re-plan adds `previous` and `changes`)."""
    main = story.story
    epic = f"{story.epic.key} {story.epic.summary}" if story.epic else "(none)"
    done = [f"- {item.key}  {item.summary} ({item.status})" for item in story.subtasks if item.done]
    docs = f"{docs_dir}/" if docs_dir else "(none: the project has no docs folder)"
    lines = [
        f"Plan the story {main.key}.",
        "",
        "## Project",
        f"Project folder: {project_root}",
        f"Base branch: {base_branch}",
        f"Docs folder: {docs}",
        f"Story budget: {_money(budget)}",
        "",
        "## Story",
        f"--- BEGIN STORY {main.key} ---",
        f"Title: {main.summary}",
        f"Epic: {epic}",
        "",
        _cut(main.description, MAX_STORY_CHARS),
        "--- END STORY ---",
        "",
        "## Open sub-tasks, in Jira's order",
        "",
        "\n\n".join(_subtask(item) for item in story.open_subtasks()),
        "",
        "## Done in Jira (context only, not planned)",
        "\n".join(done) or "(none)",
    ]
    if previous:
        lines += ["", f"## Your previous plan (run {previous['run_id']})", _previous_plan(previous)]
    if changes and changes.strip():
        lines += [
            "",
            "## Changes asked for by the person who reviews the plan",
            "--- BEGIN CHANGES ---",
            _clean(changes),
            "--- END CHANGES ---",
        ]
    return "\n".join([*lines, "", "## Tracked files of the project", files])


def fix_prompt(problems: str) -> str:
    """The message that sends a refused answer back once."""
    return (
        f"{SYSTEM_MARKER}\n"
        "Your answer was checked and cannot be saved:\n"
        f"{problems}\n"
        "Fix these points and send the whole JSON object again."
    )
