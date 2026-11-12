"""Sync from Jira: bring a space's epics, stories and sub-tasks into tracker_items.

Only the board's shape is copied: key, type, parent, summary and status. Descriptions,
acceptance criteria and links are read live from Jira when a story is checked or planned
(core/trackers/jira/story.py), so a fix made in Jira is seen without another sync.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from core.db.repositories.tracker_items import BoardItem, SyncCounts, replace_board
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient, quote_jql
from core.trackers.models import Issue

SYNC_FIELDS = ["summary", "issuetype", "parent", "status"]
MAX_ITEMS = 5000


class SyncError(TrackerError):
    """The sync was refused before anything was written."""


@dataclass(frozen=True)
class SyncResult:
    space: str
    epics: int
    stories: int
    subtasks: int
    counts: SyncCounts
    synced_at: datetime

    def describe(self) -> str:
        return (
            f"Synced {self.space}: {self.epics} epics, {self.stories} stories, "
            f"{self.subtasks} sub-tasks ({self.counts.describe()})."
        )


def board_items(client: JiraClient, space: str) -> list[BoardItem]:
    """Every work item of the space, read from Jira, as rows for tracker_items."""
    jql = f"project = {quote_jql(space)} ORDER BY key ASC"
    issues = client.search(jql, limit=MAX_ITEMS + 1, fields=SYNC_FIELDS)
    if len(issues) > MAX_ITEMS:
        # Stopping is safer than a partial copy: items past the limit would look deleted.
        raise SyncError(
            f"Jira space {space} has more than {MAX_ITEMS} work items; "
            "sync stopped and nothing was changed."
        )
    return [_board_item(issue) for issue in issues]


def _board_item(issue: Issue) -> BoardItem:
    return BoardItem(issue.key, issue.kind, issue.summary, issue.status, issue.parent_key)


def sync_board(
    session: Session,
    project_id: int,
    client: JiraClient,
    space: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> SyncResult:
    """Read the space from Jira, then replace the project's tracker_items in one transaction.

    Jira is read completely before the first write, so a Jira error changes nothing.
    """
    if not space:
        raise SyncError("JIRA_PROJECT_KEY is empty in .env: no Jira space to sync.")
    items = board_items(client, space)
    stamp = now().replace(tzinfo=None)  # the database keeps UTC without a zone
    counts = replace_board(session, project_id, items, stamp)
    kinds = [item.type for item in items]
    return SyncResult(
        space,
        kinds.count("epic"),
        kinds.count("story"),
        kinds.count("sub-task"),
        counts,
        stamp,
    )
