"""Tracker items as Brigade sees them, whatever the tracker."""

from dataclasses import dataclass
from typing import Any


def _name(value: Any) -> str | None:
    return value.get("name") if isinstance(value, dict) else None


def kind_of(issue_type: dict) -> str:
    """Jira's work type as one of epic | story | sub-task.

    Nothing is invented: Jira says which level the type sits at (1 epic, 0 standard, -1 sub-task).
    The names differ between sites ("Subtask" / "Sub-task"), and a site can add its own (Task,
    Bug), but the database and the Publisher rules need exactly these three. Level 0 types
    other than Story count as stories.
    """
    level = issue_type.get("hierarchyLevel")
    if level == 1:
        return "epic"
    if level == -1 or issue_type.get("subtask") is True:
        return "sub-task"
    return "story"


@dataclass(frozen=True)
class Issue:
    key: str
    kind: str  # the Jira work type as epic | story | sub-task (the projects schema's `type`)
    summary: str
    description: str = ""
    status: str | None = None
    parent_key: str | None = None
    labels: tuple[str, ...] = ()
    priority: str | None = None
    due_date: str | None = None  # YYYY-MM-DD
    subtask_keys: tuple[str, ...] = ()

    @classmethod
    def from_jira(cls, payload: dict) -> "Issue":
        # Imported here, not at the top: importing core.trackers.jira loads the client, which
        # imports this module, so a top-level import fails when this module is imported first.
        from core.trackers.jira.adf import adf_to_text

        fields = payload.get("fields") or {}
        issue_type = fields.get("issuetype") or {}
        parent = fields.get("parent") or {}
        return cls(
            key=str(payload["key"]),
            kind=kind_of(issue_type),
            summary=str(fields.get("summary") or ""),
            description=adf_to_text(fields.get("description")).strip(),
            status=_name(fields.get("status")),
            parent_key=parent.get("key"),
            labels=tuple(fields.get("labels") or ()),
            priority=_name(fields.get("priority")),
            due_date=fields.get("duedate"),
            subtask_keys=tuple(s["key"] for s in fields.get("subtasks") or () if "key" in s),
        )


# ---------- One story, read for planning ----------


@dataclass(frozen=True)
class Link:
    """One side of a Jira issue link, seen from the item that has it."""

    kind: str  # the link type's name, e.g. "Blocks"
    phrase: str  # how it reads from this item, e.g. "is blocked by"
    key: str  # the other item
    summary: str = ""


@dataclass(frozen=True)
class WorkItem:
    """A story or sub-task with what planning needs: text, criteria and links."""

    key: str
    type: str  # Jira's own type name (Story, Subtask, Task...)
    summary: str
    description: str
    status: str
    done: bool  # Jira's status category is Done
    labels: tuple[str, ...]
    priority: str | None
    url: str
    links: tuple[Link, ...] = ()
    acceptance_criteria: str | None = None
    blocked_by: tuple[str, ...] = ()  # sibling sub-tasks this one "is blocked by"


@dataclass(frozen=True)
class Epic:
    key: str
    summary: str


@dataclass(frozen=True)
class Story:
    story: WorkItem
    epic: Epic | None
    subtasks: tuple[WorkItem, ...] = ()

    def open_subtasks(self) -> tuple[WorkItem, ...]:
        return tuple(item for item in self.subtasks if not item.done)
