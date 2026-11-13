from pathlib import Path

from pydantic import SecretStr

from core.settings import Settings
from core.trackers.models import Epic, Story, WorkItem
from pipeline.planning import readiness as r
from tests.doubles.jira import FakeJira
from tests.pipeline.workspace.repo import git, make_repo

CRITERIA = "- it works"
CLAUDE = "## Project structure\n## Commands\n## Rules\n"


def item(
    key, criteria: str | None = CRITERIA, done=False, blocked_by=(), summary="Do it", description=""
):
    return WorkItem(
        key=key,
        type="Subtask",
        summary=summary,
        description=description,
        status="Done" if done else "To Do",
        done=done,
        labels=(),
        priority=None,
        url="",
        acceptance_criteria=criteria,
        blocked_by=tuple(blocked_by),
    )


def story(*subtasks, summary="Export skills", description="") -> Story:
    main = item("SMT-10", None, summary=summary, description=description)
    return Story(main, Epic("SMT-2", "Profile"), tuple(subtasks))


def statuses(checks, group):
    return [(c.status, c.what) for c in checks if c.group == group]


# ---------- Story ----------


def test_a_ready_story():
    found = r.check_story(story(item("SMT-11"), item("SMT-12", blocked_by=["SMT-11"])))
    assert all(c.status == r.OK for c in found)
    assert found[-1].detail == "1 link between the sub-tasks"


def test_no_subtasks_fails():
    (only,) = r.check_story(story())
    assert only.status == r.FAILED and "nothing to plan" in only.detail


def test_all_done_fails():
    found = r.check_story(story(item("SMT-11", done=True)))
    assert found[-1].status == r.FAILED and "Every sub-task is Done" in found[-1].detail


def test_done_subtasks_are_left_out_and_not_checked():
    found = r.check_story(story(item("SMT-11", criteria=None, done=True), item("SMT-12")))
    assert found[1].detail == "Done in Jira and left out: SMT-11"
    assert all(c.status == r.OK for c in found)


def test_missing_criteria_names_the_subtasks():
    found = r.check_story(story(item("SMT-11", criteria=None), item("SMT-12", criteria=None)))
    failed = [c for c in found if c.status == r.FAILED]
    assert len(failed) == 1 and failed[0].detail.startswith("Missing in SMT-11, SMT-12.")


def test_forbidding_text_fails():
    found = r.check_story(story(item("SMT-11"), description="Do not modify any files."))
    failed = [c for c in found if c.status == r.FAILED]
    assert failed[0].what == "The text does not forbid the work"
    assert failed[0].detail.startswith("SMT-10 forbids modifications")


def test_looping_links_fail():
    found = r.check_story(
        story(
            item("SMT-11", blocked_by=["SMT-12"]),
            item("SMT-12", blocked_by=["SMT-11"]),
            item("SMT-13", blocked_by=["SMT-11"]),
        )
    )
    assert found[-1].status == r.FAILED
    assert found[-1].detail == "These wait for each other: SMT-11, SMT-12."


# ---------- Checkout ----------


def test_clean_checkout_on_main(tmp_path):
    repo = make_repo(tmp_path / "proj")
    found = r.check_checkout(repo, "main")
    assert [c.status for c in found] == [r.OK, r.OK, r.OK]


def test_not_a_repository(tmp_path):
    (tmp_path / "plain").mkdir()
    (only,) = r.check_checkout(tmp_path / "plain", "main")
    assert only.status == r.FAILED and "not inside a Git repository" in only.detail


def test_unknown_base_branch(tmp_path):
    repo = make_repo(tmp_path / "proj")
    (only,) = r.check_checkout(repo, "develop")
    assert only.status == r.FAILED and "BRIGADE_BASE_BRANCH" in only.detail


def test_uncommitted_changes_and_another_branch(tmp_path):
    repo = make_repo(tmp_path / "proj")
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "new.txt").write_text("x", encoding="utf-8")
    found = r.check_checkout(repo, "main")
    assert statuses(found, "Checkout")[1:] == [
        (r.FAILED, "No uncommitted changes"),
        (r.FAILED, "On main"),
    ]
    assert "(first: new.txt)" in found[1].detail
    assert "on feature" in found[2].detail


# ---------- Tests and the whole run ----------


def settings(
    tmp_path: Path,
    *,
    project_path: Path | None = None,
    docs_dir: str = "docs",
    jira_project_key: str = "",
    jira_site_url: str = "",
    jira_email: str = "",
    jira_api_token: str = "",
) -> Settings:
    """Settings for the tests only: defaults plus these values, never the real .env."""
    return Settings.model_construct(
        data_dir=tmp_path / "data",
        test_timeout=60,
        project_path=project_path,
        docs_dir=docs_dir,
        jira_project_key=jira_project_key,
        jira_site_url=jira_site_url,
        jira_email=jira_email,
        jira_api_token=SecretStr(jira_api_token),
    )


def ready_project(tmp_path):
    repo = make_repo(tmp_path / "proj")
    (repo / "CLAUDE.md").write_text(CLAUDE, encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "a.md").write_text("doc", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "docs")
    return repo


def test_everything_ready(tmp_path):
    repo = ready_project(tmp_path)
    config = settings(tmp_path, project_path=repo, docs_dir="docs")
    result = r.run_checks(story(item("SMT-11")), config)
    assert result.ready and not result.warnings
    text = r.format_checks(result)
    assert text.startswith("Checks before planning SMT-10")
    assert text.endswith("Ready to plan.")


def test_a_dirty_checkout_fails_the_run_of_checks(tmp_path):
    repo = ready_project(tmp_path)
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    config = settings(tmp_path, project_path=repo, docs_dir="docs")
    result = r.run_checks(story(item("SMT-11")), config)
    assert not result.ready
    assert r.format_checks(result).endswith(
        "1 check failed; nothing was planned. Fix the lines marked FAIL and check again."
    )


def test_no_project_folder(tmp_path):
    result = r.run_checks(story(item("SMT-11")), settings(tmp_path))
    assert ("failed", "A project folder is set") in statuses(result.checks, "Checkout")
    assert not result.ready


# ---------- the command line ----------


def test_main_reads_the_story_and_exits_by_result(tmp_path, monkeypatch, capsys):
    repo = ready_project(tmp_path)
    jira = (
        FakeJira()
        .add("SMT-10", "story", "Export", "SMT-2")
        .add("SMT-11", "sub-task", "Formatter", "SMT-10", "Acceptance criteria:\n- works")
        .add("SMT-12", "sub-task", "Command", "SMT-10", "No criteria")
    )
    config = settings(tmp_path, project_path=repo, jira_project_key="SMT")
    monkeypatch.setattr(r, "get_settings", lambda: config)
    monkeypatch.setattr(r.JiraClient, "from_settings", classmethod(lambda c, s: jira.client()))
    assert r.main(["SMT-10"]) == 2
    assert "Missing in SMT-12." in capsys.readouterr().out
    assert r.main(["SMT-99"]) == 1
    assert "Could not read SMT-99" in capsys.readouterr().err
