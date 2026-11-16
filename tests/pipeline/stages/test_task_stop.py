"""Stop and Cancel inside one task: the agent is stopped, the word kept, nothing paid after."""

import pytest

from core.db import get_session
from core.db.repositories import merge_rows
from core.runs import run_directory
from pipeline.control import task_control as tc
from pipeline.runner.claude_runner import AgentStopped
from pipeline.stages import checkpoint, interrupt, task_run
from pipeline.stages.attempt_log import attempt_dir
from pipeline.workspace import layout
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import TeamRunner, team_project

KEY = "SMT-62"


class AskingRunner(TeamRunner):
    """The Team fake, where a person asks when a given agent is called, as the page would.

    kill=True: the agent was running when the request came, so the real runner would kill it and
    raise AgentStopped, which is what this raises. kill=False: it finishes before it is noticed."""

    def __init__(self, repo, role, action, *, kill=True, **more):
        super().__init__(**more)
        self.folder = run_directory(repo, RUN)
        self.role, self.action, self.kill = role, action, kill

    def run(self, request):
        if request.agent == self.role:
            tc.ask(self.folder, KEY, self.action)
            if self.kill:
                self.requests.append(request)
                raise AgentStopped(f"The {request.agent} agent was stopped on request.")
        return super().run(request)


def newest(engine):
    with get_session(engine) as session:
        sub, attempt = merge_rows.newest_attempt(session, RUN, KEY)
        return sub.status, sub.current_stage, attempt.outcome, attempt.reason


def test_a_stop_asked_before_the_task_starts_starts_nothing(tmp_path):
    repo, config, engine = team_project(tmp_path)
    tc.ask(run_directory(repo, RUN), KEY, tc.STOP)
    runner = TeamRunner()
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert (stopped.value.state, stopped.value.stage) == (tc.STOPPED, "builder")
    assert runner.requests == []
    with get_session(engine) as session:
        assert merge_rows.newest_attempt(session, RUN, KEY) is None  # no attempt was made
    word = tc.settled(run_directory(repo, RUN), KEY)
    assert (word.state, word.stage) == (tc.STOPPED, "builder")


def test_a_stop_while_the_builder_runs_keeps_the_builder_to_run_again(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "builder", tc.STOP)
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert (stopped.value.state, stopped.value.stage) == (tc.STOPPED, "builder")
    assert [r.agent for r in runner.requests] == ["builder"]  # nothing after it was paid
    status, stage, outcome, reason = newest(engine)
    assert (status, stage, outcome) == ("stopped", "builder", "stopped")
    assert "Stopped by request" in reason
    assert checkpoint.completed(repo, RUN, KEY, 1) == []
    assert tc.pending(run_directory(repo, RUN), KEY) is None  # the request was spent


def test_every_task_stage_gets_the_stage_stop_asked_in_it(tmp_path):
    """Stop in the tester: the builder and the checks are kept, the tester runs again."""
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "tester", tc.STOP)
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert stopped.value.stage == "tester"
    assert [r.agent for r in runner.requests] == ["builder", "tester"]
    assert checkpoint.completed(repo, RUN, KEY, 1) == ["builder", "checks"]
    assert checkpoint.resume_stage(repo, RUN, KEY, 1) == "tester"
    assert newest(engine)[2] == "stopped"


def test_a_stop_after_the_tester_finished_continues_at_the_judge(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "tester", tc.STOP, kill=False)  # it finished before it was seen
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert stopped.value.stage == "judge"  # nothing of the tester is paid again
    assert [r.agent for r in runner.requests] == ["builder", "tester"]
    assert checkpoint.completed(repo, RUN, KEY, 1) == ["builder", "checks", "tester"]


def test_a_stop_while_the_reviewer_runs_stops_at_the_judge(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "reviewer", tc.STOP)
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert stopped.value.stage == "judge"
    assert newest(engine)[2] == "stopped"  # not left as 'needs review'


def test_a_cancel_is_final_and_keeps_the_work_where_it_is(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "builder", tc.CANCEL)
    with pytest.raises(interrupt.TaskInterrupted) as cancelled:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert cancelled.value.state == tc.CANCELLED
    assert tc.settled(run_directory(repo, RUN), KEY).state == tc.CANCELLED
    status, _, outcome, reason = newest(engine)
    assert (status, outcome) == ("cancelled", "cancelled") and "Cancelled by request" in reason
    with get_session(engine) as session:
        attempt = merge_rows.newest_attempt(session, RUN, KEY)[1]
        assert attempt.branch  # the branch is still named on the row
    assert layout.attempt_worktree(config.worktrees_dir, RUN, KEY, 1).is_dir()  # kept to look at


def test_a_stop_that_comes_after_the_judge_said_done_is_too_late(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "reviewer", tc.STOP, kill=False)
    done = task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert done.ok  # it finished: the task goes on to be merged
    assert tc.pending(run_directory(repo, RUN), KEY) is None
    assert tc.settled(run_directory(repo, RUN), KEY) is None
    assert newest(engine)[2] == "done"


def test_a_cancel_that_comes_after_the_judge_said_done_still_wins(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "reviewer", tc.CANCEL, kill=False)
    with pytest.raises(interrupt.TaskInterrupted) as cancelled:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert cancelled.value.state == tc.CANCELLED
    assert newest(engine)[2] == "cancelled"  # nothing is merged


def test_a_run_nobody_stops_is_not_changed_at_all(tmp_path):
    repo, config, engine = team_project(tmp_path)
    done = task_run.run_task(config, RUN, KEY, TeamRunner(), engine=engine)
    assert done.ok
    assert checkpoint.completed(repo, RUN, KEY, 1) == ["builder", "checks", "tester"]
    assert not (run_directory(repo, RUN) / tc.FOLDER).exists()
    assert attempt_dir(repo, RUN, KEY, 1).is_dir()


def test_the_stop_file_is_handed_to_every_agent_of_the_task(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner()
    task_run.run_task(config, RUN, KEY, runner, engine=engine)
    wanted = interrupt.stop_file_of(repo, RUN, KEY)
    assert [r.stop_file for r in runner.requests] == [wanted] * 3
