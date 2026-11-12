"""The Planning tab's left and middle panes: epics, their stories and sub-tasks, from
tracker_items (the last Sync), with each story's newest run."""

from dataclasses import dataclass, field
from datetime import datetime

from core.db.models import StoryRun, TrackerItem

NO_EPIC = "No epic"


@dataclass
class StoryNode:
    item: TrackerItem
    subtasks: list[TrackerItem] = field(default_factory=list)
    latest_run: StoryRun | None = None


@dataclass
class EpicNode:
    key: str | None  # None: stories whose epic is not on the board
    summary: str
    status: str | None
    stories: list[StoryNode] = field(default_factory=list)


@dataclass(frozen=True)
class TreeView:
    space: str
    last_synced: datetime | None
    epics: list[EpicNode]


def build_tree(
    space: str,
    rows: list[TrackerItem],
    latest: dict[str, StoryRun],
    last_synced: datetime | None,
) -> TreeView:
    """Rows come parents first (tracker_items.board), so each parent exists before its children."""
    epics = {
        row.key: EpicNode(row.key, row.summary, row.status) for row in rows if row.type == "epic"
    }
    loose = EpicNode(None, NO_EPIC, None)
    stories: dict[str, StoryNode] = {}
    for row in rows:
        if row.type == "story":
            node = StoryNode(row, latest_run=latest.get(row.key))
            stories[row.key] = node
            epics.get(row.parent_key or "", loose).stories.append(node)
        elif row.type == "sub-task" and row.parent_key in stories:
            stories[row.parent_key].subtasks.append(row)
    shown = list(epics.values()) + ([loose] if loose.stories else [])
    return TreeView(space, last_synced, shown)
