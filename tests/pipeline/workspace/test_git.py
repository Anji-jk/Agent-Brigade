import pytest

from pipeline.workspace import git as g
from tests.pipeline.workspace.repo import git, make_repo


@pytest.mark.parametrize("ref", ["main", "release/2.0", "feature_x-1"])
def test_good_base_branches(ref):
    assert g.validate_base_ref(ref) == ref


@pytest.mark.parametrize("ref", ["", "-x", "a..b", "main/", "x.lock", "has space", "a;b"])
def test_bad_base_branches_are_refused(ref):
    with pytest.raises(g.GitError, match="BRIGADE_BASE_BRANCH"):
        g.validate_base_ref(ref)


def test_repository_root_from_a_subfolder(tmp_path):
    repo = make_repo(tmp_path / "proj")
    (repo / "src").mkdir()
    assert g.repository_root(repo / "src") == repo.resolve()


def test_repository_root_refuses_missing_and_plain_folders(tmp_path):
    with pytest.raises(g.GitError, match="is not a folder"):
        g.repository_root(tmp_path / "missing")
    (tmp_path / "plain").mkdir()
    with pytest.raises(g.GitError, match="not inside a Git repository"):
        g.repository_root(tmp_path / "plain")


def test_commit_branch_head_and_changes(tmp_path):
    repo = make_repo(tmp_path / "proj")
    head = g.head_commit(repo)
    assert g.commit_of(repo, "main") == head
    assert g.commit_of(repo, "nope") is None
    assert g.current_branch(repo) == "main"
    assert g.changed_files(repo) == []
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    (repo / "new.txt").write_text("x", encoding="utf-8")
    assert sorted(g.changed_files(repo)) == ["README.md", "new.txt"]


def test_detached_head_has_no_branch(tmp_path):
    repo = make_repo(tmp_path / "proj")
    git(repo, "checkout", "-q", "--detach")
    assert g.current_branch(repo) == ""


def test_a_failing_git_command_says_which(tmp_path):
    repo = make_repo(tmp_path / "proj")
    with pytest.raises(g.GitError, match="git rev-parse failed"):
        g.run_git(repo, "rev-parse", "--verify", "nope")


def test_repository_state_changes_with_a_new_file_or_branch(tmp_path):
    repo = make_repo(tmp_path / "r")
    before = g.repository_state(repo)
    assert before == g.repository_state(repo)
    (repo / "new.txt").write_text("x", encoding="utf-8")
    assert g.repository_state(repo)["status"] != before["status"]
    (repo / "new.txt").unlink()
    git(repo, "branch", "other")
    assert g.repository_state(repo)["branches"] != before["branches"]


def test_tracked_files_are_listed_and_cut_with_a_note(tmp_path):
    repo = make_repo(tmp_path / "r")
    for name in ("a.py", "b.py", "c.py"):
        (repo / name).write_text("x", encoding="utf-8")
    git(repo, "add", ".")
    assert g.tracked_files(repo, 1000).splitlines() == ["README.md", "a.py", "b.py", "c.py"]
    cut = g.tracked_files(repo, 14)
    assert cut.splitlines()[:2] == ["README.md", "a.py"]
    assert "2 more files not listed" in cut
