import pytest

from core.db import get_session
from core.db.repositories import merge_rows
from core.runs import run_directory
from pipeline.control import task_control as tc
from pipeline.stages import checkpoint, interrupt
from pipeline.stages.builder_run import build_attempt
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import TeamRunner, built_and_checked, team_project

KEY = "SMT-62"


def outcome(engine):
    with get_session(engine) as session:
        sub, attempt = merge_rows.newest_attempt(session, RUN, KEY)
        return sub.status, attempt.outcome


def test_with_no_request_the_guard_lets_the_task_go_on(tmp_path):
    repo, config, engine = team_project(tmp_path)
    interrupt.guard(engine, repo, RUN, KEY, 1, "builder")  # raises nothing
    assert tc.settled(run_directory(repo, RUN), KEY) is None


def test_the_guard_raises_with_the_state_and_where_the_task_resumes(tmp_path):
    repo, config, engine = team_project(tmp_path)
    tc.ask(run_directory(repo, RUN), KEY, tc.STOP)
    with pytest.raises(interrupt.TaskInterrupted) as stopped:
        interrupt.guard(engine, repo, RUN, KEY, 1, "checks")
    assert (stopped.value.state, stopped.value.stage) == (tc.STOPPED, "checks")


def test_settling_an_open_attempt_marks_it_but_never_rewrites_a_decision_of_the_judge(tmp_path):
    repo, config, engine = team_project(tmp_path, verify=('python -c "import sys; sys.exit(3)"',))
    built_and_checked(repo, config, engine, TeamRunner())
    assert outcome(engine) == ("running", "built")
    interrupt.settle_task(engine, repo, RUN, KEY, tc.CANCELLED, "tester", 1)
    assert outcome(engine) == ("cancelled", "cancelled")  # 'built' was open: marked
    with get_session(engine) as session:  # now give it a verdict of the judge
        sub, attempt = merge_rows.newest_attempt(session, RUN, KEY)
        attempt.outcome = "failed"
    interrupt.settle_task(engine, repo, RUN, KEY, tc.CANCELLED, "judge", 1)
    assert outcome(engine)[1] == "failed"  # a Cancel of a failed task keeps what the judge said
    interrupt.settle_task(engine, repo, RUN, KEY, tc.CANCELLED, "judge", 1, force=True)
    assert outcome(engine)[1] == "cancelled"  # unless the attempt was in flight (force)


def test_settling_names_only_the_attempt_it_was_asked_about(tmp_path):
    repo, config, engine = team_project(tmp_path)
    build_attempt(config, RUN, KEY, TeamRunner(), engine=engine)
    interrupt.settle_task(engine, repo, RUN, KEY, tc.STOPPED, "tester", 7, force=True)
    assert outcome(engine)[1] == "built"  # attempt 7 is not the newest one: nothing is rewritten
    assert tc.settled(run_directory(repo, RUN), KEY).attempt == 7


def test_a_task_with_no_attempt_is_settled_to_resume_from_the_builder(tmp_path):
    repo, config, engine = team_project(tmp_path)
    state, stage = interrupt.settle_waiting(engine, repo, RUN, KEY, tc.CANCEL)
    assert (state, stage) == (tc.CANCELLED, "builder")
    assert tc.settled(run_directory(repo, RUN), KEY).attempt is None


def test_a_task_with_a_checkpoint_resumes_from_the_first_stage_not_finished(tmp_path):
    repo, config, engine = team_project(tmp_path)
    build_attempt(config, RUN, KEY, TeamRunner(), engine=engine)
    checkpoint.save(repo, RUN, KEY, 1, "builder")
    checkpoint.save(repo, RUN, KEY, 1, "checks")
    assert interrupt.settle_waiting(engine, repo, RUN, KEY, tc.STOP) == (tc.STOPPED, "tester")
    word = tc.settled(run_directory(repo, RUN), KEY)
    assert (word.stage, word.attempt) == ("tester", 1)
    assert outcome(engine) == ("stopped", "stopped")
