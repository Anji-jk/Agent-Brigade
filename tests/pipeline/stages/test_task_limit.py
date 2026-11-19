"""An agent that hits its turn, time or dollar limit stops its task so that Continue can go on."""

import pytest

from core.db import get_session
from core.db.repositories import attempt_rows, merge_rows
from core.runs import run_directory
from pipeline.control import task_control as tc
from pipeline.runner.claude_runner import AgentError, AgentLimit, AgentReply
from pipeline.stages import checkpoint, interrupt, task_run
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import TeamRunner, team_project

KEY = "SMT-62"
SPENT = AgentReply(
    "", "s", cost_usd=2.14, turns=100, duration_ms=60_000, model_used="claude-sonnet"
)


class LimitRunner(TeamRunner):
    """The Team fake, where `role` runs out of its limit the first `times` times it is called."""

    def __init__(self, role, limit="turns", *, times=1, partial=SPENT, **more):
        super().__init__(**more)
        self.role, self.limit, self.times, self.partial = role, limit, times, partial

    def run(self, request):
        if request.agent == self.role and self.times > 0:
            self.times -= 1
            self.requests.append(request)
            raise AgentLimit(
                f"The {request.agent} agent stopped: it reached its limit of 100 turns",
                self.limit,
                self.partial,
            )
        return super().run(request)


def newest(engine):
    with get_session(engine) as session:
        sub, attempt = merge_rows.newest_attempt(session, RUN, KEY)
        return sub.status, sub.current_stage, attempt.outcome, attempt.reason


def agent_rows(engine, role):
    with get_session(engine) as session:
        sub, attempt = merge_rows.newest_attempt(session, RUN, KEY)
        return [a for a in attempt_rows.agent_runs_of(session, attempt.id) if a.role == role]


def stop_at(tmp_path, runner_of):
    repo, config, engine = team_project(tmp_path)
    runner = runner_of(repo)
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    return repo, config, engine, runner, stopped.value


def test_a_builder_that_runs_out_of_turns_stops_its_task_instead_of_failing_it(tmp_path):
    repo, _, engine, runner, stopped = stop_at(tmp_path, lambda repo: LimitRunner("builder"))
    assert (stopped.state, stopped.stage) == (tc.STOPPED, "builder")
    assert [r.agent for r in runner.requests] == ["builder"]  # nothing after it was paid
    status, stage, outcome, reason = newest(engine)
    assert (status, stage, outcome) == ("stopped", "builder", "stopped")
    assert "limit of 100 turns" in reason and "resumes from builder" in reason
    assert checkpoint.completed(repo, RUN, KEY, 1) == []


def test_the_word_on_disk_says_which_limit_stopped_it(tmp_path):
    repo, *_ = stop_at(tmp_path, lambda repo: LimitRunner("builder"))
    word = tc.settled(run_directory(repo, RUN), KEY)
    assert (word.state, word.stage, word.attempt) == (tc.STOPPED, "builder", 1)
    assert "limit of 100 turns" in word.reason
    assert tc.pending(run_directory(repo, RUN), KEY) is None  # the note is spent


def test_what_the_agent_spent_before_the_limit_is_recorded(tmp_path):
    *_, engine, _, _ = stop_at(tmp_path, lambda repo: LimitRunner("builder"))
    (row,) = agent_rows(engine, "builder")
    assert (row.cost, row.turns, row.status) == (2.14, 100, "error")
    assert "limit of 100 turns" in row.exit_reason


def test_a_limit_with_no_usage_to_record_still_stops_the_task(tmp_path):
    *_, engine, _, stopped = stop_at(
        tmp_path, lambda repo: LimitRunner("builder", "time", partial=None)
    )
    assert stopped.state == tc.STOPPED
    assert agent_rows(engine, "builder")[0].cost is None


def test_a_tester_out_of_turns_keeps_the_builder_and_the_checks(tmp_path):
    repo, _, engine, runner, stopped = stop_at(tmp_path, lambda repo: LimitRunner("tester"))
    assert stopped.stage == "tester"
    assert [r.agent for r in runner.requests] == ["builder", "tester"]
    assert checkpoint.completed(repo, RUN, KEY, 1) == ["builder", "checks"]
    assert newest(engine)[2] == "stopped"


def test_a_reviewer_out_of_dollars_stops_at_the_judge_not_as_needs_review(tmp_path):
    repo, _, engine, _, stopped = stop_at(tmp_path, lambda repo: LimitRunner("reviewer", "budget"))
    assert stopped.stage == "judge"
    assert checkpoint.completed(repo, RUN, KEY, 1) == ["builder", "checks", "tester"]
    assert newest(engine)[2] == "stopped"


def test_a_limit_hit_in_the_second_asking_of_an_agent_stops_it_too(tmp_path):
    """The Tester's first answer is unusable, so it is asked again, and the second runs out."""
    runner = LimitRunner("tester", tester_text=["not json at all"], times=0)
    inner = runner.run
    calls = []

    def run(request):
        calls.append(request.agent)
        if request.agent == "tester" and calls.count("tester") == 2:
            raise AgentLimit("The tester agent stopped: it reached its limit", "turns", SPENT)
        return inner(request)

    runner.run = run
    repo, config, engine = team_project(tmp_path)
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert stopped.value.stage == "tester"


def test_continue_goes_on_in_the_same_attempt_with_a_fresh_allowance(tmp_path):
    repo, config, engine, runner, _ = stop_at(tmp_path, lambda repo: LimitRunner("builder"))
    done = task_run.run_task(config, RUN, KEY, runner, engine=engine, resume=True)
    assert done.ok
    assert [r.agent for r in runner.requests] == ["builder", "builder", "tester", "reviewer"]
    assert newest(engine)[2] == "done"
    with get_session(engine) as session:  # still one attempt: nothing was spent from the retries
        assert merge_rows.newest_attempt(session, RUN, KEY)[1].number == 1


def test_continue_after_a_tester_limit_does_not_pay_for_the_builder_again(tmp_path):
    repo, config, engine, runner, _ = stop_at(tmp_path, lambda repo: LimitRunner("tester"))
    done = task_run.run_task(config, RUN, KEY, runner, engine=engine, resume=True)
    assert done.ok
    assert [r.agent for r in runner.requests] == ["builder", "tester", "tester", "reviewer"]


def test_a_cancel_asked_before_the_limit_is_not_turned_into_a_stop(tmp_path):
    repo, config, engine = team_project(tmp_path)
    tc.ask(run_directory(repo, RUN), KEY, tc.CANCEL)
    runner = LimitRunner("builder")
    with pytest.raises(interrupt.TaskInterrupted) as ended:
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert ended.value.state == tc.CANCELLED


def test_a_stop_a_person_asked_while_the_agent_ran_keeps_its_own_wording(tmp_path):
    repo, config, engine = team_project(tmp_path)

    class StoppedThenLimit(LimitRunner):
        def run(self, request):
            tc.ask(run_directory(repo, RUN), KEY, tc.STOP)  # the person clicks Stop mid-run
            return super().run(request)

    with pytest.raises(interrupt.TaskInterrupted):
        task_run.run_task(config, RUN, KEY, StoppedThenLimit("builder"), engine=engine)
    assert "Stopped by request" in newest(engine)[3]
    assert tc.settled(run_directory(repo, RUN), KEY).reason is None


def test_any_other_agent_failure_is_still_an_error_for_a_person(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(errors={"builder": "Claude Code exited with code 1: boom"})
    result = task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert not result.ok and result.built is not None and result.built.error
    assert newest(engine)[2] == "error"
    assert tc.settled(run_directory(repo, RUN), KEY) is None


def test_a_plain_agent_error_is_not_a_limit():
    assert not isinstance(AgentError("boom"), AgentLimit)
