"""The Jira-owned half of a story plan: one task per open sub-task, copied from Jira.

Code builds this before the planner starts, so the planner never sees or changes the title,
description or acceptance criteria. Nothing here reads or writes Jira, Git or files.
"""

import re
from typing import Any

from core.trackers.models import Story
from pipeline.planning.plan_fields import MAX_TASKS, MAX_TEXT, MAX_TITLE, PlanValidationError

_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?")


def criteria_list(text: str | None) -> list[str]:
    """Jira's acceptance criteria, one per line, list markers removed and the words kept."""
    found = []
    for line in (text or "").splitlines():
        line = _BULLET.sub("", line).strip()
        if line:
            found.append(line)
    return found


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    marker = "\n... (cut short)"
    return text if len(text) <= limit else text[: limit - len(marker)] + marker


def jira_tasks(story: Story) -> list[dict[str, Any]]:
    """The Jira-owned part of each task, made before the planner is started."""
    items = story.open_subtasks()
    if not items:
        raise PlanValidationError(f"{story.story.key} has no open sub-tasks to plan.")
    missing = [item.key for item in items if not criteria_list(item.acceptance_criteria)]
    if missing:
        raise PlanValidationError(
            "No acceptance criteria in " + ", ".join(missing) + ". Add them in Jira; "
            "the planner was not started."
        )
    if len(items) > MAX_TASKS:
        raise PlanValidationError(f"A story plan may have at most {MAX_TASKS} open sub-tasks.")
    return [
        {
            "id": f"T{number}",
            "jira_key": item.key,
            "title": _cut(item.summary, MAX_TITLE),
            "description": _cut(item.description or item.summary, MAX_TEXT),
            "acceptance_criteria": criteria_list(item.acceptance_criteria),
        }
        for number, item in enumerate(items, 1)
    ]
