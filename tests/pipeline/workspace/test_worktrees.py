import pytest

from pipeline.workspace import worktrees as w
from pipeline.workspace.git import GitError, commit_of
from tests.pipeline.workspace.repo import git, make_repo


def repo_with_two_commits(tmp_path):
    repo = make_repo(tmp_path / "proj")
    first = git(repo, "rev-parse", "HEAD")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "second")
    return repo, first


def test_a_story_branch_and_worktree_leave_the_main_checkout_alone(tmp_path):
    repo, first = repo_with_two_commits(tmp_path)
    before = git(repo, "status", "--porcelain"), git(repo, "branch", "--show-current")
    w.create_branch(repo, "agent/r1", first)
    w.add_story_worktree(repo, tmp_path / "bw" / "r1" / "story", "agent/r1")
    assert git(repo, "rev-parse", "agent/r1") == first
    assert not (tmp_path / "bw" / "r1" / "story" / "b.txt").exists()  # the older commit
    assert (git(repo, "status", "--porcelain"), git(repo, "branch", "--show-current")) == before
    listed = w.list_worktrees(repo)
    assert [info.branch for info in listed] == ["main", "agent/r1"]


def test_a_branch_is_made_once(tmp_path):
    repo, first = repo_with_two_commits(tmp_path)
    w.create_branch(repo, "agent/r1", first)
    with pytest.raises(GitError, match="already exists"):
        w.create_branch(repo, "agent/r1", first)


def test_an_attempt_starts_at_the_story_tip_on_its_own_branch(tmp_path):
    repo, first = repo_with_two_commits(tmp_path)
    w.create_branch(repo, "agent/r1", first)
    w.add_attempt_worktree(repo, tmp_path / "bw" / "a", "agent-attempt/r1/SMT-62-1", first)
    assert git(repo, "rev-parse", "agent-attempt/r1/SMT-62-1") == first
    with pytest.raises(GitError, match="already exists"):
        w.add_attempt_worktree(repo, tmp_path / "bw" / "b", "agent-attempt/r1/SMT-62-1", first)


def test_a_folder_that_is_in_use_is_not_taken(tmp_path):
    repo, first = repo_with_two_commits(tmp_path)
    busy = tmp_path / "bw" / "x"
    busy.mkdir(parents=True)
    (busy / "file").write_text("x", encoding="utf-8")
    with pytest.raises(GitError, match="not empty"):
        w.add_attempt_worktree(repo, busy, "agent-attempt/r1/SMT-62-1", first)


def test_removing_keeps_the_branch(tmp_path):
    repo, first = repo_with_two_commits(tmp_path)
    path = tmp_path / "bw" / "a"
    w.add_attempt_worktree(repo, path, "agent-attempt/r1/SMT-62-1", first)
    w.remove_worktree(repo, path)
    assert not path.exists() and len(w.list_worktrees(repo)) == 1
    assert commit_of(repo, "refs/heads/agent-attempt/r1/SMT-62-1") == first


def test_uncommitted_work_is_not_removed_unless_asked(tmp_path):
    repo, first = repo_with_two_commits(tmp_path)
    path = tmp_path / "bw" / "a"
    w.add_attempt_worktree(repo, path, "agent-attempt/r1/SMT-62-1", first)
    (path / "new.txt").write_text("work\n", encoding="utf-8")
    with pytest.raises(GitError, match="uncommitted"):
        w.remove_worktree(repo, path)
    assert path.exists()
    w.remove_worktree(repo, path, discard_changes=True)
    assert not path.exists()


def test_the_main_checkout_and_strangers_are_never_removed(tmp_path):
    repo, _ = repo_with_two_commits(tmp_path)
    with pytest.raises(GitError, match="main checkout"):
        w.remove_worktree(repo, repo, discard_changes=True)
    stranger = tmp_path / "elsewhere"
    stranger.mkdir()
    with pytest.raises(GitError, match="not a worktree"):
        w.remove_worktree(repo, stranger, discard_changes=True)
    assert repo.exists() and stranger.exists()
