"""A story's plan file: the whole task list, the planner's answer, and saving and loading.

A plan is stored at ``<project>/.agent-brigade/runs/<run_id>/plan.json``. It is written once
and never overwritten (Re-plan makes a new run); only its ``approval`` block changes later.
Everything read back from disk or from the planner is checked again, since neither is trusted.
"""

import json
import re
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import project_folder, run_directory, utc_now
from pipeline.planning.plan_fields import MAX_TASKS, PlanValidationError, check_task
from pipeline.planning.plan_order import check_order
from pipeline.planning.project_commands import check_command_lists

SCHEMA_VERSION = 2
PLAN_FILE_NAME = "plan.json"


class PlanFileError(RuntimeError):
    """A plan file that is missing, unreadable or not the run it claims to be."""


def validate_tasks(raw_tasks: object) -> list[dict[str, Any]]:
    """Check and normalize the task list; parallel_safe may be turned off (see plan_order)."""
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise PlanValidationError("tasks must be a non-empty list.")
    if len(raw_tasks) > MAX_TASKS:
        raise PlanValidationError(f"A plan may have at most {MAX_TASKS} tasks.")
    tasks = [check_task(raw, index) for index, raw in enumerate(raw_tasks, start=1)]
    check_order(tasks)
    return tasks


# ---------- the planner's answer ----------

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _candidate_documents(text: str) -> list[str]:
    candidates = [text.strip()]
    candidates += [match.strip() for match in _FENCE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    return candidates


def parse_planner_answer(text: object) -> dict[str, Any]:
    """The JSON object in the planner's last message: bare, in a fenced block, or amid prose.

    Only finds the object; story_plan.merge_planner_output decides whether it is a usable plan.
    """
    if not isinstance(text, str) or not text.strip():
        raise PlanValidationError("The planner returned no output.")
    for candidate in _candidate_documents(text):
        try:
            document = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(document, dict):
            return document
    raise PlanValidationError("The planner's output did not contain a JSON object.")


# ---------- the file ----------


def plan_path(project_root: Path, run_id: str) -> Path:
    return run_directory(project_root, run_id) / PLAN_FILE_NAME


def save_plan(project_root: Path, run_id: str, document: dict[str, Any]) -> Path:
    """Write a new plan. Never overwrites: a plan that exists stays as it is."""
    path = plan_path(project_root, run_id)
    if path.exists():
        raise FileExistsError(f"A plan already exists for run {run_id}: {path}")
    record = {
        "schema_version": SCHEMA_VERSION,
        **document,
        "run_id": run_id,
        "created_at": utc_now(),
    }
    record["tasks"] = validate_tasks(record.get("tasks"))  # check what is about to be written
    record["commands"] = check_command_lists(record.get("commands"))
    project_folder(project_root)  # .agent-brigade/ with its .gitignore
    write_json_atomic(path, record)
    return path


def load_plan(project_root: Path, run_id: str) -> dict[str, Any]:
    """Read a stored plan and check it again."""
    path = plan_path(project_root, run_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PlanFileError(f"No plan found for run {run_id}.") from None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise PlanFileError(f"Plan file is unreadable or malformed: {run_id}") from None
    if not isinstance(record, dict) or record.get("run_id") != run_id:
        raise PlanFileError(f"Plan file does not match its run id: {run_id}")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise PlanFileError(
            f"Unsupported plan schema version: {record.get('schema_version')!r} "
            f"(this version reads {SCHEMA_VERSION}; plan the story again)."
        )
    try:
        record["tasks"] = validate_tasks(record.get("tasks"))
        record["commands"] = check_command_lists(record.get("commands"))  # older plans: none
    except PlanValidationError as exc:
        raise PlanFileError(f"Stored plan is invalid: {exc}") from None
    return record


def save_approval(project_root: Path, run_id: str, approval: dict[str, Any]) -> dict[str, Any]:
    """Replace the plan's ``approval`` block; every other part of plan.json stays as it is.

    Approve calls this after each Jira link it writes, so a stop half-way keeps what was done.
    """
    load_plan(project_root, run_id)  # the same checks as reading it
    path = plan_path(project_root, run_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record.get("approval"), dict):
        raise PlanFileError(f"Run {run_id} is not a plan that waits for approval.")
    record["approval"] = approval
    write_json_atomic(path, record)
    return load_plan(project_root, run_id)
