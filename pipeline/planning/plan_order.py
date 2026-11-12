"""How a plan's tasks relate: ids, dependencies, order, and what may run at once.

``check_order`` raises PlanValidationError for a duplicate task or sub-task, a dependency on
nothing or on itself, or a cycle. It then switches off ``parallel_safe`` where code cannot
confirm it, which only ever reduces what runs at the same time.
"""

from pathlib import PurePosixPath
from typing import Any

from pipeline.planning.plan_fields import PlanValidationError


def check_order(tasks: list[dict[str, Any]]) -> None:
    """Check the tasks against each other; ``parallel_safe`` may be turned off in place."""
    _reject_duplicates(tasks)
    _check_dependencies(tasks)
    _reject_cycles(tasks)
    _enforce_parallel_safety(tasks)


def _twice(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def _reject_duplicates(tasks: list[dict[str, Any]]) -> None:
    ids = _twice([task["id"] for task in tasks])
    if ids:
        raise PlanValidationError(f"Duplicate task ids: {', '.join(ids)}.")
    keys = _twice([task["jira_key"] for task in tasks if "jira_key" in task])
    if keys:
        raise PlanValidationError(f"Sub-task in two tasks: {', '.join(keys)}.")


def _check_dependencies(tasks: list[dict[str, Any]]) -> None:
    known = {task["id"] for task in tasks}
    for task in tasks:
        for dependency in task["depends_on"]:
            if dependency == task["id"]:
                raise PlanValidationError(f"Task {task['id']} depends on itself.")
            if dependency not in known:
                raise PlanValidationError(
                    f"Task {task['id']} depends on missing task {dependency!r}."
                )
        if len(set(task["depends_on"])) != len(task["depends_on"]):
            raise PlanValidationError(f"Task {task['id']} lists a dependency twice.")
        extra = set(task.get("dependency_reasons", {})) - set(task["depends_on"])
        if extra:
            raise PlanValidationError(
                f"Task {task['id']} gives a reason for a task it does not depend on: "
                f"{', '.join(sorted(extra))}."
            )


def _reject_cycles(tasks: list[dict[str, Any]]) -> None:
    """Kahn's algorithm: whatever cannot be put in order is part of a cycle."""
    remaining = {task["id"]: set(task["depends_on"]) for task in tasks}
    while remaining:
        ready = [task_id for task_id, deps in remaining.items() if not deps]
        if not ready:
            raise PlanValidationError(
                "Task dependencies contain a cycle: " + ", ".join(sorted(remaining)) + "."
            )
        for task_id in ready:
            del remaining[task_id]
        for deps in remaining.values():
            deps.difference_update(ready)


def _ancestors(tasks: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Every task each task depends on, directly or through others."""
    direct = {task["id"]: set(task["depends_on"]) for task in tasks}
    result: dict[str, set[str]] = {}

    def visit(task_id: str) -> set[str]:
        if task_id not in result:
            found: set[str] = set()
            for parent in direct[task_id]:
                found |= {parent} | visit(parent)
            result[task_id] = found
        return result[task_id]

    for task_id in direct:
        visit(task_id)
    return result


def _normalized_files(task: dict[str, Any]) -> set[str]:
    return {
        PurePosixPath(path.replace("\\", "/")).as_posix().lower().removeprefix("./")
        for path in task["files"]
    }


def _enforce_parallel_safety(tasks: list[dict[str, Any]]) -> None:
    """The planner's parallel_safe is kept only when code can confirm it.

    A task stays parallel-safe only if it names its files and shares none with any task it
    is not ordered against (neither depends on the other, directly or through others). A task
    that names no files makes every unordered task unsafe, since overlap cannot be ruled out.
    Turning it off only means less running at once, so it can never cause a conflict.
    """
    ancestors = _ancestors(tasks)
    files = {task["id"]: _normalized_files(task) for task in tasks}
    for task in tasks:
        if not task["parallel_safe"]:
            continue
        mine = files[task["id"]]
        safe = bool(mine)
        for other in tasks:
            if not safe:
                break
            if other["id"] == task["id"]:
                continue
            if other["id"] in ancestors[task["id"]] or task["id"] in ancestors[other["id"]]:
                continue
            theirs = files[other["id"]]
            safe = bool(theirs) and not (mine & theirs)
        task["parallel_safe"] = safe
