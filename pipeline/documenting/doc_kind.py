"""Which task of a plan is the documentation task.

Planning is not changed: the orchestrator looks at the title Jira already gave the task. The
Publisher writes every documentation sub-task as 'Documentation: ...' (the guard insists on it),
so the title is the one signal the saved plan already carries. A hand-made sub-task titled
differently is simply not recognised, and its story gets the fallback report instead.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from pipeline.publisher.guard import DOC_PREFIX


def is_documentation_title(title: object) -> bool:
    """True when the title starts with 'Documentation:' (case and leading spaces ignored)."""
    return isinstance(title, str) and title.strip().casefold().startswith(DOC_PREFIX)


def is_documentation_task(task: Mapping[str, Any]) -> bool:
    """True for a plan task (one entry of plan.json 'tasks') that is the documentation task."""
    return is_documentation_title(task.get("title"))


def documentation_keys(tasks: Iterable[Mapping[str, Any]]) -> list[str]:
    """The Jira keys of the documentation tasks of a plan, in plan order."""
    return [
        str(task["jira_key"])
        for task in tasks
        if is_documentation_task(task) and task.get("jira_key")
    ]
