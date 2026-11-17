"""The story loop with Continue: a stopped task goes on in its own attempt, a live loop or a new."""

import threading
import time
from concurrent.futures import Future

from sqlalchemy import select

from core.db import get_session
from core.db.models import Attempt, SubTask
from core.runs import run_directory
from pipeline.control import continue_request as cont
from pipeline.control import task_control as tc
from pipeline.stages import story_loop as s
from pipeline.stages.attempt_resume import RESUME_NOTE
from pipeline.stages.story_report import MERGED, PAUSED, WAITING
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.test_story_loop import HoldingRunner, StoryRunner, kinds, project
from tests.pipeline.stages.test_story_loop_stop import AskingHolding, AskingStory


def attempts(engine):
    with get_session(engine) as session:
        rows = session.execute(
            select(SubTask.key, Attempt.number, Attempt.outcome)
            .join(Attempt, Attempt.sub_task_id == SubTask.id)
            .order_by(Attempt.id)
        )
        return [tuple(row) for row in rows]


class StopOnceHolding(AskingHolding):
    """A person's Stop comes the first time that task's Builder is called, as in real life."""

    fired = False

    def run(self, request):
        if self.fired:
            return HoldingRunner.run(self, request)
        if request.agent == self.role and self.key in str(request.cwd):
            self.fired = True
        return super().run(request)


def test_a_new_loop_continues_a_stopped_task_in_the_same_attempt(tmp_path):
    repo, config, engine = project(tmp_path)
    s.run_story(config, RUN, AskingStory(repo, "SMT-62", tc.STOP), engine=engine)
    folder = run_directory(repo, RUN)
    cont.release(folder, "SMT-62", 1)  # what Continue does before it starts a loop
    runner = StoryRunner()
    result = s.run_story(config, RUN, runner, engine=engine)
    assert result.ok and result.statuses() == {"SMT-62": MERGED, "SMT-63": MERGED}
    assert [r.agent for r in runner.requests if "SMT-62" in str(r.cwd)][0] == "builder"
    first = next(r for r in runner.requests if "SMT-62" in str(r.cwd))
    assert RESUME_NOTE in first.prompt  # told that the worktree already holds work
    assert attempts(engine) == [("SMT-62", 1, "done"), ("SMT-63", 1, "done")]  # no new attempt
    assert "task_continued" in kinds(repo, "SMT-62")
    assert cont.wanted(folder, "SMT-62") is None  # the note did its work
    assert not (folder / "control" / "SMT-62.json").exists()


def test_a_new_loop_deletes_the_report_of_the_old_one_before_it_starts(tmp_path):
    repo, config, engine = project(tmp_path)
    s.run_story(config, RUN, AskingStory(repo, "SMT-62", tc.STOP), engine=engine)
    report = run_directory(repo, RUN) / "story-report.json"
    assert report.exists()
    seen = []

    class Looking(StoryRunner):
        def run(self, request):
            seen.append(report.exists())
            return super().run(request)

    cont.release(run_directory(repo, RUN), "SMT-62", 1)
    s.run_story(config, RUN, Looking(), engine=engine)
    assert seen and seen[0] is False  # a crash now would read as interrupted, not as paused


def test_a_loop_that_is_running_puts_a_continued_task_back_to_work(tmp_path):
    repo, config, engine = project(tmp_path, together=True)
    folder = run_directory(repo, RUN)
    runner = StopOnceHolding(repo, "SMT-62", tc.STOP, hold=0.6)
    outcome = {}
    loop = threading.Thread(
        target=lambda: outcome.update(r=s.run_story(config, RUN, runner, engine=engine))
    )
    loop.start()
    deadline = time.monotonic() + 20
    while not tc.settled(folder, "SMT-62") and time.monotonic() < deadline:
        time.sleep(0.02)
    settled = tc.settled(folder, "SMT-62")
    assert settled is not None
    assert settled.state == tc.STOPPED  # stopped; SMT-63 still holds the loop
    cont.release(folder, "SMT-62", 1)
    loop.join(timeout=60)
    assert outcome["r"].statuses() == {"SMT-62": MERGED, "SMT-63": MERGED}
    assert sorted(attempts(engine)) == [("SMT-62", 1, "done"), ("SMT-63", 1, "done")]
    assert kinds(repo, "SMT-62").count("task_released") == 1


def test_a_stopped_task_nobody_continued_stays_stopped_in_a_live_loop(tmp_path):
    repo, config, engine = project(tmp_path)
    loop = s._Loop(config, RUN, StoryRunner(), engine)
    loop.hearing.interrupted("SMT-62", tc.STOPPED, "builder")
    tc.settle(run_directory(repo, RUN), "SMT-62", tc.STOPPED, "builder", 1)
    assert loop.hearing.released("SMT-62") is False
    assert loop.result.tasks["SMT-62"].status == PAUSED


def test_a_task_stopped_before_it_had_an_attempt_simply_starts_when_continued(tmp_path):
    repo, config, engine = project(tmp_path)
    folder = run_directory(repo, RUN)
    tc.ask(folder, "SMT-62", tc.STOP)  # before anything ran
    s.run_story(config, RUN, StoryRunner(), engine=engine)
    settled = tc.settled(folder, "SMT-62")
    assert settled is not None
    assert settled.attempt is None
    cont.release(folder, "SMT-62", None)
    runner = StoryRunner()
    result = s.run_story(config, RUN, runner, engine=engine)
    assert result.ok
    assert not any(RESUME_NOTE in r.prompt for r in runner.requests)  # a normal first attempt
    assert attempts(engine) == [("SMT-62", 1, "done"), ("SMT-63", 1, "done")]


def test_a_continued_task_waits_for_its_turn_like_any_other(tmp_path):
    repo, config, engine = project(tmp_path)
    s.run_story(config, RUN, AskingStory(repo, "SMT-62", tc.STOP), engine=engine)
    cont.release(run_directory(repo, RUN), "SMT-62", 1)
    loop = s._Loop(config, RUN, StoryRunner(), engine)
    loop.running["SMT-99"] = (Future(), 1)  # a place is taken
    loop.limit = 1
    task = loop.plan["tasks"][0]
    assert loop.can_start(task, resume=True) is False  # no free place: it waits, nothing is paid
    assert loop.result.tasks["SMT-62"].status == WAITING
