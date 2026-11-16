import pytest

from pipeline.workspace.lock import LockError, merge_lock, run_lock


def test_a_second_story_loop_on_the_same_run_is_refused(tmp_path):
    with run_lock(tmp_path), pytest.raises(LockError, match="story loop is already running"):
        with run_lock(tmp_path):
            pass


def test_the_lock_is_released_when_the_loop_ends_even_by_an_error(tmp_path):
    with pytest.raises(RuntimeError), run_lock(tmp_path):
        raise RuntimeError("boom")
    with run_lock(tmp_path):
        assert (tmp_path / "story.lock").is_file()
    assert not (tmp_path / "story.lock").exists()


def test_the_refusal_names_the_file_to_delete_after_a_crash(tmp_path):
    with run_lock(tmp_path), pytest.raises(LockError, match=r"story\.lock"):
        with run_lock(tmp_path):
            pass


def test_the_story_lock_and_the_merge_lock_do_not_block_each_other(tmp_path):
    with run_lock(tmp_path), merge_lock(tmp_path):
        pass
