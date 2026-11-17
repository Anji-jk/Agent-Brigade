"""Continue as a note: the Stop is taken back, the attempt to go on with is named."""

import pytest

from pipeline.control import continue_request as cont
from pipeline.control import task_control as tc

KEY = "SMT-62"


def test_continue_takes_the_stop_back_and_names_the_attempt(tmp_path):
    tc.settle(tmp_path, KEY, tc.STOPPED, "tester", 2)
    cont.release(tmp_path, KEY, 2)
    assert tc.settled(tmp_path, KEY) is None
    assert cont.wanted(tmp_path, KEY) == 2


def test_a_task_stopped_before_it_had_an_attempt_leaves_no_note(tmp_path):
    tc.settle(tmp_path, KEY, tc.STOPPED, "builder", None)
    cont.release(tmp_path, KEY, None)
    assert tc.settled(tmp_path, KEY) is None
    assert cont.wanted(tmp_path, KEY) is None


def test_spent_removes_the_note_and_is_safe_twice(tmp_path):
    cont.release(tmp_path, KEY, 1)
    cont.spent(tmp_path, KEY)
    cont.spent(tmp_path, KEY)
    assert cont.wanted(tmp_path, KEY) is None


@pytest.mark.parametrize("text", ["", "nope", "[]", '{"attempt": true}', '{"attempt": "2"}'])
def test_a_damaged_note_names_no_attempt(tmp_path, text):
    path = tmp_path / "control" / f"{KEY}.continue"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    assert cont.wanted(tmp_path, KEY) is None


def test_a_key_that_is_not_a_jira_key_is_refused(tmp_path):
    with pytest.raises(ValueError):
        cont.release(tmp_path, "../x", 1)
