"""The story loop with a person's Stop and Cancel: who waits, who is blocked, who carries on."""

import json

from core.runs import run_directory
from pipeline.control import task_control as tc
from pipeline.runner.claude_runner import AgentStopped
from pipeline.stages import story_loop as s
from pipeline.stages.story_report import BLOCKED, CANCELLED, MERGED, PAUSED, WAITING
from tests.pipeline.stages.stage_setup import FAIL, RUN
from tests.pipeline.stages.test_story_loop import HoldingRunner, StoryRunner, kinds, project


class Asked:
    """Mixin: when `key`'s `role` agent is called, a person asks `action`; the agent is killed."""

    def __init__(self, repo, key, action, role="builder", **more):
        super().__init__(**more)
        self.folder, self.key, self.action, self.role = run_directory(repo, RUN), key, action, role

    def run(self, request):
        if request.agent == self.role and self.key in str(request.cwd):
            tc.ask(self.folder, self.key, self.action)
            raise AgentStopped("stopped on request")
        return getattr(super(), "run")(request)


class AskingStory(Asked, StoryRunner):
    pass


class AskingHolding(Asked, HoldingRunner):
    pass


def report(repo):
    return json.loads((run_directory(repo, RUN) / "story-report.json").read_text())


def test_a_stopped_task_pauses_the_story_and_what_depends_on_it_only_waits(tmp_path):
    repo, config, engine = project(tmp_path)
    runner = AskingStory(repo, "SMT-62", tc.STOP)
    result = s.run_story(config, RUN, runner, engine=engine)
    assert not result.ok
    assert result.statuses() == {"SMT-62": PAUSED, "SMT-63": WAITING}  # waiting, not blocked
    assert "Continue resumes from the builder stage" in result.tasks["SMT-62"].detail
    assert not any("SMT-63" in str(r.cwd) for r in runner.requests)  # nothing spent on it
    assert report(repo)["tasks"]["SMT-62"]["status"] == "stopped"
    assert "task_paused" in kinds(repo, "SMT-62") and "story_stopped" in kinds(repo)


def test_a_cancelled_task_is_final_and_blocks_what_depends_on_it(tmp_path):
    repo, config, engine = project(tmp_path)
    result = s.run_story(config, RUN, AskingStory(repo, "SMT-62", tc.CANCEL), engine=engine)
    assert result.statuses() == {"SMT-62": CANCELLED, "SMT-63": BLOCKED}
    assert "SMT-62" in result.tasks["SMT-63"].detail
    assert "task_cancelled" in kinds(repo, "SMT-62")


def test_an_independent_task_carries_on_while_another_is_stopped(tmp_path):
    repo, config, engine = project(tmp_path, together=True)
    runner = AskingHolding(repo, "SMT-62", tc.STOP, hold=0.1)
    result = s.run_story(config, RUN, runner, engine=engine)
    assert result.statuses() == {"SMT-62": PAUSED, "SMT-63": MERGED}


def test_starting_the_loop_again_keeps_a_stopped_task_stopped_and_pays_nothing(tmp_path):
    repo, config, engine = project(tmp_path)
    s.run_story(config, RUN, AskingStory(repo, "SMT-62", tc.STOP), engine=engine)
    again = StoryRunner()
    result = s.run_story(config, RUN, again, engine=engine)
    assert result.statuses() == {"SMT-62": PAUSED, "SMT-63": WAITING}
    assert again.requests == []  # the word was on disk: a second loop does not undo it


def test_a_request_for_a_task_that_has_not_started_is_settled_by_the_loop(tmp_path):
    repo, config, engine = project(tmp_path, depends=False, together=True)
    tc.ask(run_directory(repo, RUN), "SMT-63", tc.CANCEL)
    runner = HoldingRunner(hold=0.1)
    result = s.run_story(config, RUN, runner, engine=engine)
    assert result.statuses() == {"SMT-62": MERGED, "SMT-63": CANCELLED}
    assert not any("SMT-63" in str(r.cwd) for r in runner.requests)
    assert tc.pending(run_directory(repo, RUN), "SMT-63") is None  # the request is spent


def test_a_cancel_between_done_and_merge_wins_and_nothing_is_merged(tmp_path):
    repo, config, engine = project(tmp_path)
    loop = s._Loop(config, RUN, StoryRunner(), engine)
    tc.ask(run_directory(repo, RUN), "SMT-62", tc.CANCEL)
    assert loop.hearing.late_request("SMT-62", 1) is True
    assert loop.result.tasks["SMT-62"].status == CANCELLED
    settled = tc.settled(run_directory(repo, RUN), "SMT-62")
    assert settled is not None
    assert settled.state == tc.CANCELLED


def test_a_stop_between_done_and_merge_is_too_late_and_is_dropped(tmp_path):
    repo, config, engine = project(tmp_path)
    loop = s._Loop(config, RUN, StoryRunner(), engine)
    tc.ask(run_directory(repo, RUN), "SMT-62", tc.STOP)
    assert loop.hearing.late_request("SMT-62", 1) is False
    assert tc.pending(run_directory(repo, RUN), "SMT-62") is None
    assert tc.settled(run_directory(repo, RUN), "SMT-62") is None


def test_a_cancel_for_a_task_that_could_never_start_is_still_a_cancel_not_a_block(tmp_path):
    repo, config, engine = project(tmp_path, first_verify=(FAIL,), max_retries=0)
    tc.ask(run_directory(repo, RUN), "SMT-63", tc.CANCEL)
    result = s.run_story(config, RUN, StoryRunner(), engine=engine)
    assert result.statuses()["SMT-63"] == CANCELLED  # a person's word, not "SMT-62 failed"