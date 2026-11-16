import pytest

from pipeline.stages import loop_start as ls
from pipeline.stages.prepare import prepare_story
from pipeline.stages.prepare_report import FAILED, OK, Prepared, StepResult
from tests.pipeline.stages.stage_setup import RUN, approved_project


def step(status):
    return StepResult("npm ci", status, 0 if status == OK else 1, 1.0, "")


def prepared(setup=OK, baseline=OK):
    result = Prepared(RUN, f"agent/{RUN}", "abc", "C:/bw/story")
    result.setup, result.baseline = [step(setup)], [step(baseline)]
    return result


class Calls:
    def __init__(self, result):
        self.calls, self.result = [], result

    def prepare(self, settings, run_id):
        self.calls.append("prepare")
        return self.result, "report.json"

    def run(self, settings, run_id, runner, engine=None):
        self.calls.append("story")
        return "STORY"


def test_a_run_is_prepared_only_after_its_story_worktree_exists(tmp_path):
    _, config, _ = approved_project(tmp_path)
    assert not ls.is_prepared(config, RUN)
    prepare_story(config, RUN)
    assert ls.is_prepared(config, RUN)


def test_an_unprepared_run_is_prepared_and_then_built(tmp_path):
    _, config, _ = approved_project(tmp_path)
    fake = Calls(prepared())
    done = ls.start_loop(config, RUN, None, prepare=fake.prepare, run=fake.run)
    assert fake.calls == ["prepare", "story"]
    assert done.story == "STORY" and done.prepared is fake.result and done.warnings == []


def test_a_prepared_run_goes_straight_to_the_story(tmp_path):
    _, config, _ = approved_project(tmp_path)
    prepare_story(config, RUN)
    fake = Calls(prepared())
    done = ls.start_loop(config, RUN, None, prepare=fake.prepare, run=fake.run)
    assert fake.calls == ["story"] and done.prepared is None


def test_a_failed_setup_stops_before_any_agent_is_paid_for(tmp_path):
    _, config, _ = approved_project(tmp_path)
    fake = Calls(prepared(setup=FAILED))
    with pytest.raises(ls.LoopStartError, match="Setup failed.*npm ci"):
        ls.start_loop(config, RUN, None, prepare=fake.prepare, run=fake.run)
    assert fake.calls == ["prepare"]


def test_a_baseline_that_already_fails_is_reported_and_the_story_goes_on(tmp_path):
    _, config, _ = approved_project(tmp_path)
    fake = Calls(prepared(baseline=FAILED))
    done = ls.start_loop(config, RUN, None, prepare=fake.prepare, run=fake.run)
    assert fake.calls == ["prepare", "story"]
    assert (
        len(done.warnings) == 1
        and "npm ci" in done.warnings[0]
        and "Already failing" in done.warnings[0]
    )
