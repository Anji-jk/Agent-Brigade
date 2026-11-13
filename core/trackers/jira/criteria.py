"""Acceptance criteria in a Jira description: the lines under an "Acceptance criteria" label.

The Publisher writes them that way. They end at the next known label, such as Dependencies or
Notes. A description without them gives None; the checks before planning decide what that means.
"""

import re

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
