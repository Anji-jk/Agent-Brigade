from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from core.db import get_session, init_db, make_engine
from core.db.models import Project, TrackerItem
from core.settings import Settings
from core.trackers.jira import __main__ as cli
from core.trackers.jira import sync as sync_module
from core.trackers.jira.sync import SyncError, board_items, sync_board
from tests.doubles.jira import FakeJira

NOW = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)


def board() -> FakeJira:
    return (
        FakeJira()
        .add("SMT-2", "epic", "Profile")
        .add("SMT-10", "story", "Export", "SMT-2")
        .add("SMT-11", "sub-task", "Formatter", "SMT-10", "Acceptance criteria:\n- works")
        .add("KAN-1", "story", "Another space")
    )


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


def test_board_items_reads_only_the_space():
    items = board_items(board().client(), "SMT")
    assert [(i.key, i.type, i.parent_key) for i in items] == [
        ("SMT-2", "epic", None),
        ("SMT-10", "story", "SMT-2"),
        ("SMT-11", "sub-task", "SMT-10"),
    ]


def test_sync_writes_the_board_and_counts_kinds(engine, project_id):
    with get_session(engine) as s:
        result = sync_board(s, project_id, board().client(), "SMT", now=lambda: NOW)
    assert (result.epics, result.stories, result.subtasks) == (1, 1, 1)
    assert result.synced_at == datetime(2026, 11, 12, 6, 0)
    assert result.describe() == (
        "Synced SMT: 1 epics, 1 stories, 1 sub-tasks (3 added, 0 updated, 0 unchanged, 0 removed)."
    )
    with get_session(engine) as s:
        assert set(s.scalars(select(TrackerItem.key))) == {"SMT-2", "SMT-10", "SMT-11"}


def test_a_jira_error_changes_nothing(engine, project_id):
    jira = board()
    with get_session(engine) as s:
        sync_board(s, project_id, jira.client(), "SMT")
    jira.down = True
    with pytest.raises(Exception, match="unreachable"):
        with get_session(engine) as s:
            sync_board(s, project_id, jira.client(), "SMT")
    with get_session(engine) as s:
        assert len(list(s.scalars(select(TrackerItem)))) == 3


def test_a_space_over_the_limit_is_refused(engine, project_id, monkeypatch):
    monkeypatch.setattr(sync_module, "MAX_ITEMS", 2)
    with pytest.raises(SyncError, match="more than 2 work items"):
        with get_session(engine) as s:
            sync_board(s, project_id, board().client(), "SMT")
    with get_session(engine) as s:
        assert list(s.scalars(select(TrackerItem))) == []


def test_an_empty_space_key_is_refused(engine, project_id):
    with pytest.raises(SyncError, match="JIRA_PROJECT_KEY is empty"):
        with get_session(engine) as s:
            sync_board(s, project_id, board().client(), "")


# ---------- the command line ----------


def settings(tmp_path, *, with_project: bool = True) -> Settings:
    """Settings for the tests only: defaults plus these values, never the real .env."""
    return Settings.model_construct(
        jira_project_key="SMT",
        project_path=tmp_path / "sm" if with_project else None,
        data_dir=tmp_path / "data",
        project_name="Skill Matrix",
    )


def test_cli_sync_and_story(tmp_path):
    jira, config = board(), settings(tmp_path)
    lines = cli.sync(jira.client(), config)
    assert lines[0].startswith("Synced SMT: 1 epics, 1 stories, 1 sub-tasks")
    assert lines[1].startswith("Last synced: ") and lines[1].endswith(" UTC")
    assert (tmp_path / "data" / "brigade.db").is_file()
    text = cli.story(jira.client(), config, "smt-10")[0]
    assert "Sub-tasks: 1 (1 open)" in text and "        - works" in text


def test_cli_sync_needs_a_project(tmp_path):
    with pytest.raises(SyncError, match="BRIGADE_PROJECT_PATH is empty"):
        cli.sync(board().client(), settings(tmp_path, with_project=False))


def test_cli_main_reports_errors_without_a_traceback(tmp_path, monkeypatch, capsys):
    jira = board()
    monkeypatch.setattr(cli, "get_settings", lambda: settings(tmp_path))
    monkeypatch.setattr(cli.JiraClient, "from_settings", classmethod(lambda c, s: jira.client()))
    assert cli.main(["story", "SMT-99"]) == 1
    assert "Jira story failed: SMT-99 was not found" in capsys.readouterr().err
    assert cli.main(["story", "SMT-10"]) == 0
    assert "Story:   SMT-10  Export" in capsys.readouterr().out
