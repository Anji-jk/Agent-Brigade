"""Read one Jira story for planning: the story, its epic and every sub-task. Reads only.

Ported from Agent Lab (orchestrator/jira/story.py).

* the story: summary, description as text, status, labels, priority, links
* its epic (the story's parent): key and summary
* each sub-task, in the order the story lists them: the same fields, the acceptance criteria
  taken from its description, and the sibling sub-tasks it "is blocked by"

Acceptance criteria are the lines under an "Acceptance criteria" label in the description (the
Publisher writes them that way), up to the next known label such as Dependencies or Notes. A
sub-task without them is still read; the checks before planning decide what that means.

Dependencies come from Jira's issue links: a "Blocks" link read as "is blocked by". Text such as
"Dependencies: <name>" stays in the description for the planner.
"""

import re
from dataclasses import replace
from typing import Any

from core.trackers.errors import TrackerError
from core.trackers.jira.adf import adf_to_text
from core.trackers.jira.client import JiraClient
from core.trackers.models import Epic, Link, Story, WorkItem

STORY_KEY = re.compile(r"[A-Z][A-Z0-9_]{0,9}-[1-9][0-9]{0,9}")
ITEM_FIELDS = [
    "summary",
    "description",
    "issuetype",
    "status",
    "labels",
    "priority",
    "parent",
    "issuelinks",
]
STORY_FIELDS = [*ITEM_FIELDS, "subtasks"]
MAX_SUBTASKS = 200  # a story with more is not a story
_BLOCKS, _BLOCKED_BY = "blocks", "is blocked by"
_SECTION_LABELS = (
    "acceptance criteria",
    "dependencies",
    "dependency",
    "labels",
    "label",
    "priority",
    "description",
    "business context",
    "context",
    "notes",
    "note",
    "definition of done",
    "proposed sub-tasks",
    "proposed subtasks",
    "sub-tasks",
    "subtasks",
    "technical notes",
    "out of scope",
    "assumptions",
    "risks",
    "source links",
    "sources",
)
_LABEL_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*|[-*]\s+)?(?:\*\*)?(?P<label>[A-Za-z][A-Za-z -]*?)"
    r"(?:\*\*)?\s*:(?:\*\*)?\s*(?P<rest>.*)$"
)
_HEADING_LINE = re.compile(r"^\s*#{1,6}\s*(?P<label>[A-Za-z][A-Za-z -]*?)\s*$")


class StoryError(TrackerError):
    """The key does not name a story that can be read. The message says why."""


def check_story_key(key: str, space: str | None = None) -> str:
    """A key such as SMT-9, upper case, in the given Jira space."""
    key = (key or "").strip().upper()
    if not STORY_KEY.fullmatch(key):
        raise StoryError(f"{key or '(empty)'} is not a Jira key such as SMT-9.")
    if space and key.split("-")[0] != space.upper():
        raise StoryError(
            f"{key} is not in the Jira space {space.upper()} (JIRA_PROJECT_KEY in .env)."
        )
    return key


def acceptance_criteria(description: str) -> str | None:
    """The lines under an "Acceptance criteria" label, up to the next known label."""
    found: list[str] = []
    inside = False
    for line in description.splitlines():
        label, rest = _label(line)
        if label == "acceptance criteria":
            inside = True
            if rest:
                found.append(rest)
            continue
        if inside and label is not None:
            break
        if inside:
            found.append(line)
    lines = "\n".join(found).strip("\n").splitlines()
    if not any(line.strip() for line in lines):
        return None
    indent = min(len(line) - len(line.lstrip()) for line in lines if line.strip())
    return "\n".join(line[indent:] for line in lines).strip() or None


def _label(line: str) -> tuple[str | None, str]:
    """(the known label this line starts with, the text after it), or (None, "")."""
    for pattern in (_HEADING_LINE, _LABEL_LINE):
        match = pattern.match(line)
        if match:
            label = re.sub(r"\s+", " ", match.group("label")).strip().lower()
            if label in _SECTION_LABELS:
                return label, (match.groupdict().get("rest") or "").strip()
    return None, ""


def _links(fields: dict[str, Any]) -> tuple[Link, ...]:
    links: list[Link] = []
    for link in fields.get("issuelinks") or []:
        if not isinstance(link, dict):
            continue
        kind = link.get("type") or {}
        for side, phrase in (
            ("inwardIssue", kind.get("inward")),
            ("outwardIssue", kind.get("outward")),
        ):
            other = link.get(side)
            if isinstance(other, dict) and other.get("key"):
                summary = (other.get("fields") or {}).get("summary") or ""
                links.append(
                    Link(
                        str(kind.get("name") or ""),
                        str(phrase or ""),
                        str(other["key"]),
                        str(summary),
                    )
                )
    return tuple(links)


def _item(data: dict[str, Any], client: JiraClient) -> WorkItem:
    fields = data.get("fields") or {}
    key = str(data.get("key") or "")
    status = fields.get("status") or {}
    description = adf_to_text(fields.get("description")).strip()
    return WorkItem(
        key=key,
        type=str((fields.get("issuetype") or {}).get("name") or ""),
        summary=str(fields.get("summary") or "").strip(),
        description=description,
        status=str(status.get("name") or ""),
        done=str((status.get("statusCategory") or {}).get("key") or "") == "done",
        labels=tuple(str(x) for x in fields.get("labels") or []),
        priority=(fields.get("priority") or {}).get("name"),
        url=client.browse_url(key),
        links=_links(fields),
        acceptance_criteria=acceptance_criteria(description),
    )


def _blocked_by(item: WorkItem, siblings: set[str]) -> tuple[str, ...]:
    """Sibling sub-tasks this one "is blocked by" (the inward side of a Blocks link)."""
    keys = (
        link.key
        for link in item.links
        if link.kind.lower() == _BLOCKS
        and link.phrase.lower() == _BLOCKED_BY
        and link.key in siblings
        and link.key != item.key
    )
    return tuple(dict.fromkeys(keys))


def _refuse_non_story(key: str, fields: dict[str, Any]) -> None:
    kind = fields.get("issuetype") or {}
    if kind.get("subtask") or kind.get("hierarchyLevel") == -1:
        parent = (fields.get("parent") or {}).get("key")
        where = f"; plan its story {parent} instead." if parent else "; plan its story instead."
        raise StoryError(f"{key} is a sub-task{where}")
    if (kind.get("hierarchyLevel") or 0) >= 1 or str(kind.get("name") or "").lower() == "epic":
        raise StoryError(f"{key} is an epic; plan one of its stories.")


def read_story(client: JiraClient, key: str, space: str | None = None) -> Story:
    """The story, its epic and its sub-tasks."""
    key = check_story_key(key, space)
    data = client.issue_raw(key, STORY_FIELDS)
    if data is None:
        raise StoryError(f"{key} was not found in Jira, or this account cannot see it.")
    fields = data.get("fields") or {}
    _refuse_non_story(key, fields)
    story = _item(data, client)

    parent = fields.get("parent") or {}
    epic = None
    if parent.get("key"):
        epic = Epic(str(parent["key"]), str((parent.get("fields") or {}).get("summary") or ""))

    listed = [
        str(sub["key"])
        for sub in fields.get("subtasks") or []
        if isinstance(sub, dict) and sub.get("key")
    ]
    found: dict[str, WorkItem] = {}
    if listed:
        jql = f"parent = {key} ORDER BY key ASC"
        for raw in client.search_raw(jql, ITEM_FIELDS, MAX_SUBTASKS):
            item = _item(raw, client)
            found[item.key] = item
    order = listed + sorted(found.keys() - set(listed))
    siblings = set(order)
    subtasks = tuple(
        replace(found[sub], blocked_by=_blocked_by(found[sub], siblings))
        for sub in order
        if sub in found
    )
    return Story(story, epic, subtasks)


def format_story(story: Story) -> str:
    """The story as the `story` command prints it."""
    item = story.story
    details = " · ".join(
        part
        for part in (
            item.status,
            item.priority,
            f"labels {', '.join(item.labels)}" if item.labels else "",
        )
        if part
    )
    lines = [f"Story:   {item.key}  {item.summary}", f"         {details}", f"         {item.url}"]
    lines.append(
        f"Epic:    {story.epic.key}  {story.epic.summary}" if story.epic else "Epic:    (none)"
    )
    lines.append(f"Sub-tasks: {len(story.subtasks)} ({len(story.open_subtasks())} open)")
    for sub in story.subtasks:
        parts = [sub.status, *([sub.priority] if sub.priority else [])]
        if sub.labels:
            parts.append("labels " + ", ".join(sub.labels))
        lines.append(f"  {sub.key}  {sub.summary}")
        lines.append(f"      {' · '.join(parts)}")
        lines.append(f"      blocked by {', '.join(sub.blocked_by) or 'nothing'}")
        if sub.acceptance_criteria:
            lines.append("      acceptance criteria:")
            lines += [
                f"        {line}" for line in sub.acceptance_criteria.splitlines() if line.strip()
            ]
        else:
            lines.append("      acceptance criteria: NONE FOUND")
    missing = [sub.key for sub in story.open_subtasks() if not sub.acceptance_criteria]
    if not story.subtasks:
        lines.append("\nThe story has no sub-tasks.")
    elif missing:
        lines.append(
            f"\nNo acceptance criteria found in: {', '.join(missing)}. "
            'Add an "Acceptance criteria:" part to their descriptions in Jira.'
        )
    return "\n".join(lines)
