import json

import pytest

from pipeline.control import task_control as tc


def test_nothing_is_pending_or_settled_for_a_task_nobody_touched(tmp_path):
    assert tc.pending(tmp_path, "SMT-62") is None
    assert tc.settled(tmp_path, "SMT-62") is None


def test_a_request_is_left_and_read_back_and_cleared(tmp_path):
    tc.ask(tmp_path, "SMT-62", tc.STOP)
    assert tc.pending(tmp_path, "SMT-62") == tc.STOP
    assert tc.request_path(tmp_path, "SMT-62").is_file()
    tc.clear_request(tmp_path, "SMT-62")
    assert tc.pending(tmp_path, "SMT-62") is None
    tc.clear_request(tmp_path, "SMT-62")  # clearing nothing is fine


def test_a_cancel_is_never_weakened_into_a_stop(tmp_path):
    tc.ask(tmp_path, "SMT-62", tc.CANCEL)
    tc.ask(tmp_path, "SMT-62", tc.STOP)
    assert tc.pending(tmp_path, "SMT-62") == tc.CANCEL


def test_a_stop_can_be_made_into_a_cancel(tmp_path):
    tc.ask(tmp_path, "SMT-62", tc.STOP)
    tc.ask(tmp_path, "SMT-62", tc.CANCEL)
    assert tc.pending(tmp_path, "SMT-62") == tc.CANCEL


def test_a_damaged_request_counts_as_the_safe_one_a_stop(tmp_path):
    path = tc.request_path(tmp_path, "SMT-62")
    path.parent.mkdir(parents=True)
    path.write_text("{half a file", encoding="utf-8")
    assert tc.pending(tmp_path, "SMT-62") == tc.STOP


def test_settling_records_the_word_and_spends_the_request(tmp_path):
    tc.ask(tmp_path, "SMT-62", tc.STOP)
    tc.settle(tmp_path, "SMT-62", tc.STOPPED, "tester", 2)
    assert tc.pending(tmp_path, "SMT-62") is None
    settled = tc.settled(tmp_path, "SMT-62")
    assert settled is not None
    assert (settled.state, settled.stage, settled.attempt) == (tc.STOPPED, "tester", 2)
    assert settled.at


def test_tasks_do_not_share_their_words(tmp_path):
    tc.settle(tmp_path, "SMT-62", tc.CANCELLED, "builder", None)
    assert tc.settled(tmp_path, "SMT-63") is None


def test_a_damaged_or_foreign_record_reads_as_nothing(tmp_path):
    path = tmp_path / tc.FOLDER / "SMT-62.json"
    path.parent.mkdir(parents=True)
    for text in ("{broken", json.dumps({"state": "flying"}), json.dumps([1])):
        path.write_text(text, encoding="utf-8")
        assert tc.settled(tmp_path, "SMT-62") is None


@pytest.mark.parametrize("key", ["../x", "SMT-62/../../y", "smt-62", "", "SMT-0"])
def test_a_key_that_is_not_a_jira_key_never_becomes_a_path(tmp_path, key):
    with pytest.raises(ValueError):
        tc.ask(tmp_path, key, tc.STOP)
    with pytest.raises(ValueError):
        tc.settled(tmp_path, key)


def test_only_a_known_action_and_state_are_accepted(tmp_path):
    with pytest.raises(ValueError):
        tc.ask(tmp_path, "SMT-62", "pause")
    with pytest.raises(ValueError):
        tc.settle(tmp_path, "SMT-62", "done", None, None)


def test_a_request_can_say_why_it_was_made(tmp_path):
    assert tc.reason_of(tmp_path, "SMT-62") is None
    tc.ask(tmp_path, "SMT-62", tc.STOP, reason="The builder agent reached its turn limit.")
    assert tc.pending(tmp_path, "SMT-62") == tc.STOP
    assert tc.reason_of(tmp_path, "SMT-62") == "The builder agent reached its turn limit."


def test_a_request_without_a_reason_has_none(tmp_path):
    tc.ask(tmp_path, "SMT-62", tc.STOP)
    assert tc.reason_of(tmp_path, "SMT-62") is None


def test_the_reason_is_kept_in_the_settled_word_and_dropped_with_the_request(tmp_path):
    tc.ask(tmp_path, "SMT-62", tc.STOP, reason="out of turns")
    tc.settle(tmp_path, "SMT-62", tc.STOPPED, "builder", 1, reason="out of turns")
    assert tc.settled(tmp_path, "SMT-62").reason == "out of turns"
    assert tc.reason_of(tmp_path, "SMT-62") is None  # the request is spent


def test_a_settled_word_made_without_a_reason_has_none(tmp_path):
    tc.settle(tmp_path, "SMT-62", tc.STOPPED, "builder", 1)
    assert tc.settled(tmp_path, "SMT-62").reason is None
