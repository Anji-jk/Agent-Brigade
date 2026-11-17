"""A running loop beats; the page trusts a fresh beat and does not look at the process."""

import time

from pipeline.control import heartbeat
from pipeline.control.launch import loop_alive
from pipeline.control.state import RUNNING, build_state


def test_a_loop_beats_while_it_runs_and_the_file_goes_when_it_ends(tmp_path):
    with heartbeat.beating(tmp_path, every=0.05):
        time.sleep(0.2)
        assert (tmp_path / heartbeat.BEAT_FILE).exists()
        assert heartbeat.fresh(tmp_path)
    assert not (tmp_path / heartbeat.BEAT_FILE).exists()
    assert not heartbeat.fresh(tmp_path)


def test_a_beat_that_stopped_is_not_fresh(tmp_path):
    (tmp_path / heartbeat.BEAT_FILE).write_text("1")
    later = time.time() + heartbeat.FRESH + 1
    assert not heartbeat.fresh(tmp_path, now=lambda: later)
    assert heartbeat.fresh(tmp_path, now=lambda: time.time())


def test_the_page_trusts_a_fresh_beat_and_never_looks_at_the_process(tmp_path):
    (tmp_path / heartbeat.BEAT_FILE).write_text("1")

    def no_look(pid):
        raise AssertionError("the process must not be looked at")

    assert loop_alive(tmp_path, "SMT-1-x", no_look, quick=True) is True
    assert build_state(tmp_path, "SMT-1-x", no_look, quick=True) == RUNNING


def test_an_action_still_looks_at_the_process_even_with_a_fresh_beat(tmp_path):
    (tmp_path / heartbeat.BEAT_FILE).write_text("1")
    looked = []
    assert loop_alive(tmp_path, "SMT-1-x", lambda pid: looked.append(pid), quick=False) is False
    # no launch record or lock names a process here, so nothing was asked; the beat alone
    # does not make a run "alive" for an action
    assert looked == []


def test_without_a_beat_the_process_is_looked_at_as_before(tmp_path):
    (tmp_path / "story.lock").write_text("4242")
    asked = []

    def look(pid):
        asked.append(pid)
        return "python -m pipeline.stages loop SMT-1-x"

    assert loop_alive(tmp_path, "SMT-1-x", look, quick=True) is True
    assert asked == [4242]


def test_a_story_loop_beats_for_as_long_as_it_runs(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from pipeline.stages import story_loop as s
    from tests.pipeline.stages.stage_setup import RUN
    from tests.pipeline.stages.test_story_loop import StoryRunner, project

    seen = []

    @contextmanager
    def watch(folder):
        seen.append("on")
        try:
            yield
        finally:
            seen.append("off")

    monkeypatch.setattr(s, "beating", watch)
    repo, config, engine = project(tmp_path)
    s.run_story(config, RUN, StoryRunner(), engine=engine)
    assert seen == ["on", "off"]
