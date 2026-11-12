from datetime import datetime

import pytest
from sqlalchemy import select

from core.db import get_session, init_db, make_engine
from core.db.models import Project, StoryRun, SubTask, TrackerItem
from core.db.repositories.tracker_items import (
    REMOVED_STATUS,
    BoardItem,
    board,
    last_synced,
    replace_board,
)

FIRST = datetime(2026, 11, 12, 6, 0)
LATER = datetime(2026, 11, 12, 7, 30)

BOARD = [
    # children before parents on purpose: the order Jira returns must not matter
    BoardItem("SMT-11", "sub-task", "Formatter", "To Do", "SMT-10"),
    BoardItem("SMT-10", "story", "Export", "To Do", "SMT-2"),
    BoardItem("SMT-2", "epic", "Profile", "In Progress"),
]


@pytest.fixture
def engine(tmp_path):
    engine = init_db(make_engine(tmp_path / "brigade.db"))
    yield engine
    engine.dispose()


@pytest.fixture
def project_id(engine):
    with get_session(engine) as s:
        project = Project(name="Skill Matrix", local_path="C:/sm", base_branch="main")
        s.add(project)
        s.flush()
        return project.id


def rows(engine, project_id) -> dict[str, tuple]:
    with get_session(engine) as s:
        return {
            r.key: (r.type, r.summary, r.status, r.parent_key)
            for r in s.scalars(select(TrackerItem).where(TrackerItem.project_id == project_id))
        }


def sync(engine, project_id, items, now=FIRST):
    with get_session(engine) as s:
        return replace_board(s, project_id, items, now)


def test_first_sync_adds_everything_parents_first(engine, project_id):
    counts = sync(engine, project_id, BOARD)
    assert (counts.added, counts.updated, counts.removed) == (3, 0, 0)
    assert rows(engine, project_id) == {
        "SMT-2": ("epic", "Profile", "In Progress", None),
        "SMT-10": ("story", "Export", "To Do", "SMT-2"),
        "SMT-11": ("sub-task", "Formatter", "To Do", "SMT-10"),
    }


def test_second_sync_counts_changes_and_unchanged(engine, project_id):
    sync(engine, project_id, BOARD)
    changed = [BOARD[0], BoardItem("SMT-10", "story", "Export skills", "Done", "SMT-2"), BOARD[2]]
    counts = sync(engine, project_id, changed, LATER)
    assert (counts.added, counts.updated, counts.unchanged, counts.removed) == (0, 1, 2, 0)
    assert rows(engine, project_id)["SMT-10"] == ("story", "Export skills", "Done", "SMT-2")
    assert counts.describe() == "0 added, 1 updated, 2 unchanged, 0 removed"


def test_items_gone_from_jira_are_removed_children_first(engine, project_id):
    sync(engine, project_id, BOARD)
    counts = sync(engine, project_id, [BOARD[2]], LATER)
    assert counts.removed == 2
    assert rows(engine, project_id) == {"SMT-2": ("epic", "Profile", "In Progress", None)}


def test_an_item_used_by_a_run_is_kept_and_marked(engine, project_id):
    sync(engine, project_id, BOARD)
    with get_session(engine) as s:
        run = StoryRun(project_id=project_id, story_key="SMT-10", status="waiting")
        s.add(run)
        s.flush()
        s.add(SubTask(story_run_id=run.id, key="SMT-11", status="queued"))
    counts = sync(engine, project_id, [BOARD[2]], LATER)
    assert (counts.removed, counts.kept) == (0, 2)
    kept = rows(engine, project_id)
    assert kept["SMT-10"] == ("story", "Export", REMOVED_STATUS, None)
    assert kept["SMT-11"] == ("sub-task", "Formatter", REMOVED_STATUS, None)
    assert counts.describe().endswith(", 2 kept for their runs")


def test_a_parent_outside_the_board_is_left_empty(engine, project_id):
    sync(engine, project_id, [BoardItem("SMT-10", "story", "Export", "To Do", "OTHER-1")])
    assert rows(engine, project_id)["SMT-10"][3] is None


def test_a_story_can_move_to_a_new_epic(engine, project_id):
    sync(engine, project_id, BOARD)
    moved = [
        BoardItem("SMT-3", "epic", "Reports"),
        BoardItem("SMT-10", "story", "Export", "To Do", "SMT-3"),
        BoardItem("SMT-11", "sub-task", "Formatter", "To Do", "SMT-10"),
    ]
    counts = sync(engine, project_id, moved, LATER)
    assert (counts.added, counts.updated, counts.removed) == (1, 1, 1)
    assert rows(engine, project_id)["SMT-10"][3] == "SMT-3"


def test_board_order_and_last_synced(engine, project_id):
    items = [*BOARD, BoardItem("SMT-9", "story", "Nine", "To Do", "SMT-2")]
    sync(engine, project_id, items)
    with get_session(engine) as s:
        assert [r.key for r in board(s, project_id)] == ["SMT-2", "SMT-9", "SMT-10", "SMT-11"]
        assert last_synced(s, project_id) == FIRST
    sync(engine, project_id, items, LATER)
    with get_session(engine) as s:
        assert last_synced(s, project_id) == LATER


def test_never_synced_has_no_time(engine, project_id):
    with get_session(engine) as s:
        assert last_synced(s, project_id) is None
        assert board(s, project_id) == []


def test_keys_move_from_another_project(engine, project_id):
    with get_session(engine) as s:
        old = Project(name="Old name", local_path="C:/sm", base_branch="main")
        s.add(old)
        s.flush()
        old_id = old.id
    sync(engine, old_id, BOARD)
    counts = sync(engine, project_id, BOARD, LATER)
    assert counts.updated == 3
    assert set(rows(engine, project_id)) == {"SMT-2", "SMT-10", "SMT-11"}
    assert rows(engine, old_id) == {}
