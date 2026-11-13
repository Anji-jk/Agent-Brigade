from pathlib import Path

import pytest

from pipeline.workspace import layout


def test_branches_and_folders_of_a_run():
    assert layout.story_branch("SMT-61-20261113-6b1a") == "agent/SMT-61-20261113-6b1a"
    assert (
        layout.attempt_branch("SMT-61-20261113-6b1a", "SMT-62", 2)
        == "agent-attempt/SMT-61-20261113-6b1a/SMT-62-2"
    )
    root = Path("/bw")
    assert layout.story_worktree(root, "r1") == root / "r1" / "story"
    assert layout.attempt_worktree(root, "r1", "SMT-62", 1) == root / "r1" / "SMT-62-1"


def test_an_attempt_branch_is_never_under_the_story_branch():
    story = layout.story_branch("r1")
    assert not layout.attempt_branch("r1", "SMT-62", 1).startswith(story + "/")


@pytest.mark.parametrize("bad", ["../x", "a b", "", "-x"])
def test_a_bad_run_id_never_becomes_a_name(bad):
    with pytest.raises(ValueError):
        layout.story_branch(bad)


@pytest.mark.parametrize(("key", "number"), [("smt-62", 1), ("SMT-62; rm", 1), ("SMT-62", 0)])
def test_a_bad_key_or_attempt_number_is_refused(key, number):
    with pytest.raises(ValueError):
        layout.attempt_branch("r1", key, number)
