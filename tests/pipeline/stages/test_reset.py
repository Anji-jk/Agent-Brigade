import pytest

from core.runs import run_directory
from pipeline.stages import reset as x
from pipeline.stages import story_loop as s
from pipeline.stages.errors import BuildError
from pipeline.stages.prepare import clean_run, prepare_story
from pipeline.workspace.lock import run_lock
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.test_story_loop import StoryRunner, project
from tests.pipeline.workspace.repo import git


def finished(tmp_path):
    """A story that was built and merged for real, then its worktrees were cleaned."""
    repo, config, engine = project(tmp_path)
    assert s.run_story(config, RUN, StoryRunner(), engine=engine).ok
    clean_run(config, RUN, discard_changes=True)
    return repo, config, engine


def delete_branches(repo):
    names = git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads/agent",
        "refs/heads/agent-attempt",
    )
    for name in names.splitlines():
        git(repo, "branch", "-D", name)


def test_a_run_whose_branches_are_still_there_is_refused_and_told_what_to_delete(tmp_path):
    repo, config, engine = finished(tmp_path)
    with pytest.raises(BuildError) as refused:
        x.reset_run(config, RUN, engine)
    text = str(refused.value)
    assert f"git branch -D agent/{RUN}" in text and f"agent-attempt/{RUN}/SMT-62-1" in text


def test_a_run_whose_worktrees_are_still_there_is_refused_and_told_to_clean(tmp_path):
    _, config, engine = project(tmp_path)
    s.run_story(config, RUN, StoryRunner(), engine=engine)
    with pytest.raises(BuildError) as refused:
        x.reset_run(config, RUN, engine)
    assert "clean" in str(refused.value)


def test_a_story_loop_that_is_running_is_refused(tmp_path):
    repo, config, engine = finished(tmp_path)
    delete_branches(repo)
    with run_lock(run_directory(repo, RUN)), pytest.raises(Exception, match="story loop"):
        x.reset_run(config, RUN, engine)


def test_the_rows_and_the_reports_go_and_the_plan_stays(tmp_path):
    repo, config, engine = finished(tmp_path)
    delete_branches(repo)
    folder = run_directory(repo, RUN)
    assert (folder / "attempts").is_dir() and (folder / "story-report.json").is_file()
    done = x.reset_run(config, RUN, engine)
    assert sorted(p.name for p in folder.iterdir()) == ["plan.json"]
    assert done.rows["sub_tasks"] == 2 and done.rows["attempts"] == 2
    assert "plan.json" in done.text() and "2 attempts" in done.text()


def test_after_a_reset_the_story_is_built_again_not_merged_from_old_commits(tmp_path):
    repo, config, engine = finished(tmp_path)
    delete_branches(repo)
    x.reset_run(config, RUN, engine)
    prepare_story(config, RUN)
    again = StoryRunner()
    assert s.run_story(config, RUN, again, engine=engine).ok
    assert [r.agent for r in again.requests].count("builder") == 2  # both tasks, with agents


def locked(monkeypatch, name):
    """Make removing the folder `name` fail, as Windows does while Explorer or OneDrive holds it."""
    real = x.shutil.rmtree

    def refuse(path, *args, **kwargs):
        if path.name == name:
            raise PermissionError(5, "Access is denied", str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(x.shutil, "rmtree", refuse)
    monkeypatch.setattr(x.time, "sleep", lambda _seconds: None)


def test_a_folder_that_will_not_go_is_reported_not_a_crash_and_the_rest_is_removed(
    tmp_path, monkeypatch
):
    repo, config, engine = finished(tmp_path)
    delete_branches(repo)
    locked(monkeypatch, "build")
    done = x.reset_run(config, RUN, engine)
    assert [name for name, _ in done.kept] == ["build"]
    left = sorted(p.name for p in run_directory(repo, RUN).iterdir())
    assert left == ["build", "plan.json"]
    assert "build" in done.text() and "Explorer" in done.text() and "reset again" in done.text()


def test_a_second_reset_finishes_what_a_locked_folder_stopped(tmp_path, monkeypatch):
    repo, config, engine = finished(tmp_path)
    delete_branches(repo)
    with monkeypatch.context() as patch:
        locked(patch, "build")
        assert x.reset_run(config, RUN, engine).kept
    again = x.reset_run(config, RUN, engine)  # the lock is gone now
    assert not again.kept and set(again.rows.values()) == {0}
    assert [p.name for p in run_directory(repo, RUN).iterdir()] == ["plan.json"]


def test_a_folder_that_frees_itself_while_we_retry_is_removed(tmp_path, monkeypatch):
    repo, config, engine = finished(tmp_path)
    delete_branches(repo)
    real, tries = x.shutil.rmtree, []

    def busy_once(path, *args, **kwargs):
        if path.name == "build" and not tries:
            tries.append(path)
            raise PermissionError(5, "Access is denied", str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(x.shutil, "rmtree", busy_once)
    monkeypatch.setattr(x.time, "sleep", lambda _seconds: None)
    assert not x.reset_run(config, RUN, engine).kept
