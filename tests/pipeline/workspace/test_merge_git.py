import pytest

from pipeline.workspace import merge as m
from pipeline.workspace.git import head_commit
from pipeline.workspace.lock import LockError, merge_lock
from tests.pipeline.workspace.repo import git, make_repo


def commit_file(folder, name, text, message):
    (folder / name).write_text(text, encoding="utf-8")
    git(folder, "add", name)
    git(folder, "commit", "-q", "-m", message)
    return git(folder, "rev-parse", "HEAD")


def story_and_attempt(tmp_path):
    """(repo, story worktree, the attempt's commit): both start at main, the attempt has a file."""
    repo = make_repo(tmp_path / "proj")
    story = tmp_path / "story"
    git(repo, "worktree", "add", "-q", "-b", "story", str(story))
    attempt = tmp_path / "attempt"
    git(repo, "worktree", "add", "-q", "-b", "attempt", str(attempt), "story")
    return repo, story, commit_file(attempt, "a.txt", "from the attempt\n", "attempt work")


def test_is_ancestor_says_whether_a_commit_is_part_of_a_branch(tmp_path):
    repo, story, commit = story_and_attempt(tmp_path)
    assert not m.is_ancestor(repo, commit, "story")
    assert m.is_ancestor(repo, "story", commit)
    assert m.is_ancestor(repo, commit, commit)
    assert not m.is_ancestor(repo, "0" * 40, "story")


def test_fast_forward_moves_the_story_branch_to_the_commit(tmp_path):
    repo, story, commit = story_and_attempt(tmp_path)
    assert m.fast_forward(story, commit) == commit
    assert git(repo, "rev-parse", "story") == commit and (story / "a.txt").is_file()
    assert m.is_ancestor(repo, commit, "story")


def test_a_fast_forward_is_refused_once_the_story_moved(tmp_path):
    repo, story, commit = story_and_attempt(tmp_path)
    commit_file(story, "b.txt", "other task\n", "another task")
    with pytest.raises(m.GitError):
        m.fast_forward(story, commit)
    assert not (story / "a.txt").exists()


def test_a_real_merge_is_checked_before_it_is_committed(tmp_path):
    repo, story, commit = story_and_attempt(tmp_path)
    other = commit_file(story, "b.txt", "other task\n", "another task")
    m.begin_merge(story, commit)
    assert head_commit(story) == other  # nothing is committed yet ...
    assert (story / "a.txt").is_file() and (story / "b.txt").is_file()  # ... but the code is there
    tip = m.finish_merge(story, "Merge SMT-62: it")
    assert git(story, "rev-list", "--parents", "-n", "1", tip).split()[1:] == [other, commit]
    assert git(story, "log", "-1", "--format=%an|%s") == "Agent Brigade|Merge SMT-62: it"
    assert m.is_ancestor(repo, commit, "story")  # the reviewed commit itself is in the history


def test_a_conflict_aborts_and_names_the_files(tmp_path):
    repo, story, commit = story_and_attempt(tmp_path)
    other = commit_file(story, "a.txt", "from another task\n", "same file")
    with pytest.raises(m.MergeConflict) as caught:
        m.begin_merge(story, commit)
    assert caught.value.files == ["a.txt"] and "a.txt" in str(caught.value)
    assert head_commit(story) == other and m.tracked_changes(story) == []
    assert (story / "a.txt").read_text(encoding="utf-8") == "from another task\n"


def test_abort_undoes_a_merge_that_failed_its_checks(tmp_path):
    repo, story, commit = story_and_attempt(tmp_path)
    other = commit_file(story, "b.txt", "other task\n", "another task")
    m.begin_merge(story, commit)
    m.abort_merge(story)
    assert head_commit(story) == other and not (story / "a.txt").exists()
    m.abort_merge(story)  # nothing in progress: not an error


def test_untracked_files_do_not_count_as_changes(tmp_path):
    _, story, _ = story_and_attempt(tmp_path)
    (story / "dist.txt").write_text("build output", encoding="utf-8")
    assert m.tracked_changes(story) == []
    (story / "README.md").write_text("edited", encoding="utf-8")
    assert m.tracked_changes(story) == ["README.md"]


def test_the_lock_allows_one_merge_at_a_time_and_is_always_released(tmp_path):
    with merge_lock(tmp_path):
        with pytest.raises(LockError, match="Another merge holds the lock"):
            with merge_lock(tmp_path):
                pass
        assert (tmp_path / "merge.lock").is_file()
    assert not (tmp_path / "merge.lock").exists()
    with pytest.raises(RuntimeError, match="boom"), merge_lock(tmp_path):
        raise RuntimeError("boom")
    assert not (tmp_path / "merge.lock").exists()  # released although the merge crashed
