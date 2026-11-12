"""One task of a plan, field by field: the limits, the text rules, and ``check_task``.

``check_task`` returns the task normalized (trimmed text, lower-case size, unknown fields
dropped) or raises PlanValidationError naming the field. How tasks relate to each other
(dependencies, cycles, files shared) is checked in plan_order.
"""

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

COMPLEXITIES = ("small", "medium", "large")
MAX_TASKS = 30
MAX_TITLE = 200
MAX_TEXT = 4000
MAX_LIST_ITEMS = 30
MAX_ITEM = 500
TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
# A Jira work item's key, such as SMT-56.
JIRA_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]{0,9}-[1-9][0-9]{0,9}")


class PlanValidationError(ValueError):
    """The planner's answer, or a stored plan, does not fit the plan's rules."""


def _text(value: object, field: str, *, limit: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise PlanValidationError(f"{field} must be text.")
    value = value.strip()
    if required and not value:
        raise PlanValidationError(f"{field} must not be empty.")
    if len(value) > limit:
        raise PlanValidationError(f"{field} is longer than {limit} characters.")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise PlanValidationError(f"{field} must be a list of at most {MAX_LIST_ITEMS} items.")
    return [_text(item, f"{field} item", limit=MAX_ITEM) for item in value]


def _complexity(value: object, field: str) -> str:
    if not isinstance(value, str) or value.strip().lower() not in COMPLEXITIES:
        raise PlanValidationError(f"{field} must be one of: {', '.join(COMPLEXITIES)}.")
    return value.strip().lower()


def _flag(value: object, field: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise PlanValidationError(f"{field} must be true or false.")
    return value


def relative_path(value: str) -> str:
    """A path inside the repository, or PlanValidationError: nothing may point outside it."""
    if (
        PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or value.startswith(("~", "\\", "/"))
        or ".." in re.split(r"[\\/]", value)
    ):
        raise PlanValidationError(f"Path must be inside the repository: {value!r}")
    return value


def _paths(value: object, field: str) -> list[str]:
    return [relative_path(item) for item in _string_list(value, field)]


def _acceptance_criteria(value: object, label: str) -> list[str]:
    criteria = _string_list(value, f"{label} acceptance_criteria")
    if not criteria:
        raise PlanValidationError(f"{label} needs at least one acceptance criterion.")
    return criteria


def check_task(raw: object, index: int) -> dict[str, Any]:
    """One task checked and normalized. Unknown fields are dropped."""
    if not isinstance(raw, dict):
        raise PlanValidationError(f"Task {index} must be an object.")
    task_id = raw.get("id")
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
        raise PlanValidationError(f"Task {index} has an invalid id: {task_id!r}.")
    label = f"Task {task_id}"
    return {
        "id": task_id,
        "title": _text(raw.get("title"), f"{label} title", limit=MAX_TITLE),
        "description": _text(raw.get("description"), f"{label} description", limit=MAX_TEXT),
        "depends_on": _string_list(raw.get("depends_on"), f"{label} depends_on"),
        "expected_outcome": _text(
            raw.get("expected_outcome"), f"{label} expected_outcome", limit=MAX_TEXT
        ),
        "files": _paths(raw.get("files"), f"{label} files"),
        "verification": _string_list(raw.get("verification"), f"{label} verification"),
        "acceptance_criteria": _acceptance_criteria(raw.get("acceptance_criteria"), label),
        "complexity": _complexity(raw.get("complexity"), f"{label} complexity"),
        "parallel_safe": _flag(raw.get("parallel_safe"), f"{label} parallel_safe"),
        **_story_fields(raw, label),
    }


def _story_fields(raw: dict[str, Any], label: str) -> dict[str, Any]:
    """The fields a story's task has besides the common ones, each checked."""
    found: dict[str, Any] = {}
    if "jira_key" in raw:
        key = raw["jira_key"]
        if not isinstance(key, str) or not JIRA_ISSUE_KEY.fullmatch(key):
            raise PlanValidationError(f"{label} has an invalid jira_key: {key!r}.")
        found["jira_key"] = key
    if "dependency_reasons" in raw:
        reasons = raw["dependency_reasons"]
        if not isinstance(reasons, dict) or len(reasons) > MAX_LIST_ITEMS:
            raise PlanValidationError(f"{label} dependency_reasons must be an object.")
        found["dependency_reasons"] = {
            str(task_id): _text(reason, f"{label} reason for {task_id}", limit=MAX_ITEM)
            for task_id, reason in reasons.items()
        }
    if "doc_target" in raw:
        target = raw["doc_target"]
        if target is not None:
            target = relative_path(_text(target, f"{label} doc_target", limit=MAX_ITEM))
        found["doc_target"] = target
    if "context" in raw:
        context = raw["context"]
        if not isinstance(context, dict):
            raise PlanValidationError(f"{label} context must be an object.")
        found["context"] = {
            "read_first": _paths(context.get("read_first"), f"{label} read_first"),
            "notes": _text(
                context.get("notes") or "", f"{label} notes", limit=MAX_TEXT, required=False
            ),
        }
    return found
