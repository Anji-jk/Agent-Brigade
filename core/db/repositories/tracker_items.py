"""Queries for tracker_items: the local copy of one project's board.

Sync replaces a project's rows with what Jira has now. An item that left Jira is deleted, unless
a story run or a sub-task row points at it: then it stays, marked REMOVED_STATUS, so the run's
history still has its title.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db.models import StoryRun, SubTask, TrackerItem

KINDS = ("epic", "story", "sub-task")  # parents before children
REMOVED_STATUS = "Removed in Jira"


@dataclass(frozen=True)
class BoardItem:
    key: str
    type: str  # epic | story | sub-task
    summary: str
    status: str | None = None
    parent_key: str | None = None


@dataclass(frozen=True)
class SyncCounts:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    kept: int = 0  # gone from Jira but used by a run, so kept and marked

    def describe(self) -> str:
        text = (
            f"{self.added} added, {self.updated} updated, {self.unchanged} unchanged, "
            f"{self.removed} removed"
        )
        return text + (f", {self.kept} kept for their runs" if self.kept else "")


def _fields(item: BoardItem) -> tuple:
    return (item.type, item.summary, item.status, item.parent_key)


def _row_fields(row: TrackerItem) -> tuple:
    return (row.type, row.summary, row.status, row.parent_key)


def _used_by_runs(session: Session, keys: set[str]) -> set[str]:
    if not keys:
        return set()
    used = set(session.scalars(select(StoryRun.story_key).where(StoryRun.story_key.in_(keys))))
    used |= set(session.scalars(select(SubTask.key).where(SubTask.key.in_(keys))))
    return used


def replace_board(
    session: Session, project_id: int, items: list[BoardItem], now: datetime
) -> SyncCounts:
    """Make the project's rows match `items`, Jira's board as it is now."""
    present = {item.key: item for item in items}
    rows = {
        row.key: row
        for row in session.scalars(select(TrackerItem).where(TrackerItem.project_id == project_id))
    }
    # A key another project's sync wrote (the same space under a new project name) moves here.
    others = {
        row.key: row
        for row in session.scalars(
            select(TrackerItem).where(
                TrackerItem.key.in_(present.keys() - rows.keys()),
                TrackerItem.project_id != project_id,
            )
        )
    }
    added = updated = unchanged = 0
    order = {kind: number for number, kind in enumerate(KINDS)}
    for item in sorted(items, key=lambda i: order.get(i.type, len(KINDS))):
        parent = item.parent_key if item.parent_key in present else None
        item = BoardItem(item.key, item.type, item.summary, item.status, parent)
        row = rows.get(item.key) or others.get(item.key)
        if row is None:
            session.add(
                TrackerItem(
                    key=item.key,
                    project_id=project_id,
                    type=item.type,
                    parent_key=item.parent_key,
                    summary=item.summary,
                    status=item.status,
                    synced_at=now,
                )
            )
            added += 1
            session.flush()  # the parent exists before its children point at it
            continue
        if _row_fields(row) == _fields(item) and row.project_id == project_id:
            unchanged += 1
        else:
            updated += 1
        row.project_id = project_id
        row.type, row.summary, row.status, row.parent_key = _fields(item)
        row.synced_at = now
    session.flush()

    gone = rows.keys() - present.keys()
    keep = _used_by_runs(session, set(gone))
    for key in keep:
        row = rows[key]
        row.status, row.parent_key, row.synced_at = REMOVED_STATUS, None, now
    session.flush()
    # Children first, so no row is ever left pointing at a deleted one.
    doomed = sorted(gone - keep, key=lambda k: (-order.get(rows[k].type, len(KINDS)), k))
    for key in doomed:
        session.delete(rows[key])
        session.flush()
    removed = len(doomed)
    return SyncCounts(added, updated, unchanged, removed, len(keep))


def board(session: Session, project_id: int) -> list[TrackerItem]:
    """The project's rows, parents before children, then by key."""
    rows = session.scalars(select(TrackerItem).where(TrackerItem.project_id == project_id))
    order = {kind: number for number, kind in enumerate(KINDS)}
    return sorted(rows, key=lambda r: (order.get(r.type, len(KINDS)), _key_order(r.key)))


def last_synced(session: Session, project_id: int) -> datetime | None:
    return session.scalar(
        select(func.max(TrackerItem.synced_at)).where(TrackerItem.project_id == project_id)
    )


def _key_order(key: str) -> tuple[str, int]:
    space, _, number = key.rpartition("-")
    return (space, int(number)) if number.isdigit() else (key, 0)
