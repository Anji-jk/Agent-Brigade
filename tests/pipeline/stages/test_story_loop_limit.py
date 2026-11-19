"""The story loop when an agent runs out of turns, time or dollars: the task waits for a person."""

from pipeline.control import task_control as tc
from pipeline.runner.claude_runner import AgentLimit
from pipeline.stages import story_loop as s
from pipeline.stages.story_report import MERGED, PAUSED, WAITING
from tests.pipeline.stages.test_story_loop import StoryRunner, kinds, project


class RunsOut(StoryRunner):
    """The Builder of `key` runs out of turns the first time it is called."""

    def __init__(self, key="SMT-62", **more):
        super().__init__(**more)
        self.key, self.out = key, True

    def run(self, request):
        if request.agent == "builder" and self.key in str(request.cwd) and self.out:
            self.out = False
            raise AgentLimit(
                "The builder agent stopped: it reached its limit of 100 turns", "turns", None
            )
        return super().run(request)


def test_a_task_that_ran_out_of_turns_pauses_the_story_and_what_depends_on_it_waits(tmp_path):
    repo, config, engine = project(tmp_path)
    runner = RunsOut()
    result = s.run_story(config, "SMT-61-20261113-6b1a", runner, engine=engine)
    assert not result.ok
    assert result.statuses() == {"SMT-62": PAUSED, "SMT-63": WAITING}
    detail = result.tasks["SMT-62"].detail
    assert "limit of 100 turns" in detail and "Continue resumes from the builder stage" in detail
    assert not any("SMT-63" in str(r.cwd) for r in runner.requests)  # nothing spent on it
    assert "task_paused" in kinds(repo, "SMT-62")


def test_a_person_who_continues_it_gets_a_fresh_allowance_in_the_same_attempt(tmp_path):
    from core.runs import run_directory
    from pipeline.control import continue_request as cont

    repo, config, engine = project(tmp_path)
    run = "SMT-61-20261113-6b1a"
    runner = RunsOut()
    s.run_story(config, run, runner, engine=engine)
    folder = run_directory(repo, run)
    word = tc.settled(folder, "SMT-62")
    tc.unsettle(folder, "SMT-62")  # what Continue does first
    cont.release(folder, "SMT-62", word.attempt)
    result = s.run_story(config, run, runner, engine=engine)
    assert result.statuses() == {"SMT-62": MERGED, "SMT-63": MERGED}
    assert result.tasks["SMT-62"].attempts == 1  # no retry was used
