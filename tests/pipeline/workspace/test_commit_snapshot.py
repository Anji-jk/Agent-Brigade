from pipeline.workspace import commit as c
from pipeline.workspace import snapshot as s
from tests.pipeline.workspace.repo import git, make_repo


def test_only_the_named_paths_are_staged_and_committed_as_brigade(tmp_path):
    repo = make_repo(tmp_path / "p")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    (repo / "stray.log").write_text("noise\n", encoding="utf-8")
    c.stage_paths(repo, ["a.txt"])
    assert "+a" in c.staged_diff(repo) and "stray" not in c.staged_diff(repo)
    sha = c.commit_staged(repo, "SMT-1: add a", "Acceptance criteria:\n- a exists")
    assert sha == git(repo, "rev-parse", "HEAD")
    assert git(repo, "log", "-1", "--format=%an <%ae>|%cn") == (
        "Agent Brigade <agent-brigade@localhost>|Agent Brigade"
    )
    assert git(repo, "show", "--stat", "--format=", "HEAD").count("|") == 1
    assert git(repo, "status", "--porcelain") == "?? stray.log"
    assert "Acceptance criteria" in git(repo, "log", "-1", "--format=%B")


def test_a_deletion_is_staged_and_odd_names_are_taken_literally(tmp_path):
    repo = make_repo(tmp_path / "p")
    (repo / "a[1].txt").write_text("x\n", encoding="utf-8")
    (repo / "a1.txt").write_text("y\n", encoding="utf-8")
    c.stage_paths(repo, ["a[1].txt"])
    assert c.staged_diff(repo).count("+++ b/") == 1  # the pattern did not match a1.txt
    (repo / "README.md").unlink()
    c.stage_paths(repo, ["README.md"])
    assert "deleted file" in c.staged_diff(repo)


def test_staging_nothing_is_fine_and_the_diff_context_is_adjustable(tmp_path):
    repo = make_repo(tmp_path / "p")
    c.stage_paths(repo, [])
    assert c.staged_diff(repo) == ""
    (repo / "README.md").write_text("hello\nmore\n", encoding="utf-8")
    c.stage_paths(repo, ["README.md"])
    assert "\n hello\n" in c.staged_diff(repo)
    assert "\n hello\n" not in c.staged_diff(repo, context=0)


def test_an_earlier_staged_file_is_unstaged_when_the_index_is_set_again(tmp_path):
    repo = make_repo(tmp_path / "p")
    (repo / "early.txt").write_text("e\n", encoding="utf-8")
    (repo / "late.txt").write_text("l\n", encoding="utf-8")
    c.stage_paths(repo, ["early.txt"])
    c.stage_paths(repo, ["late.txt"])
    assert "late.txt" in c.staged_diff(repo) and "early.txt" not in c.staged_diff(repo)
    assert (repo / "early.txt").is_file()
    c.stage_paths(repo, [])
    assert c.staged_diff(repo) == ""


def test_commit_message_has_key_title_and_criteria():
    assert c.commit_message("SMT-9", "Do  it", ["a", "b  c"]) == (
        "SMT-9: Do it",
        "Acceptance criteria:\n- a\n- b c",
    )
    subject, body = c.commit_message("SMT-9", "x" * 300, [])
    assert len(subject) == c.SUBJECT_CHARS and subject.endswith("…") and body == ""


def test_fingerprints_tell_what_was_written_between_two_moments(tmp_path):
    repo = make_repo(tmp_path / "p")
    (repo / "mine.txt").write_text("1", encoding="utf-8")
    before = s.fingerprints(repo)
    (repo / "mine.txt").write_text("2", encoding="utf-8")  # changed
    (repo / "new.txt").write_text("n", encoding="utf-8")  # created
    (repo / "README.md").unlink()  # deleted
    after = s.fingerprints(repo)
    assert s.written_between(before, after) == ["README.md", "mine.txt", "new.txt"]
    assert s.written_between(after, after) == []


def test_restoring_a_file_to_head_counts_as_a_write(tmp_path):
    repo = make_repo(tmp_path / "p")
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    before = s.fingerprints(repo)
    git(repo, "checkout", "--", "README.md")
    assert s.written_between(before, s.fingerprints(repo)) == ["README.md"]
