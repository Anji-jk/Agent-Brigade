from core.files.atomic import write_json_atomic
from pipeline.control import task_control as tc
from pipeline.planning.plan_file import load_plan, plan_path
from pipeline.stages import interrupt
from pipeline.stages import schedule as s
from pipeline.stages.builder_run import build_attempt
from pipeline.stages.merge_run import merge_attempt
from pipeline.stages.prepare import approved_plan
from pipeline.stages.task_run import run_task
from tests.pipeline.stages.stage_setup import FAIL, RUN
from tests.pipeline.stages.team_setup import TeamRunner, team_project


def blockers(repo, engine, key):
    return s.start_blockers(repo, approved_plan(repo, RUN), RUN, key, engine)


def test_a_task_that_depends_on_nothing_may_start(tmp_path):
    repo, config, engine = team_project(tmp_path)
    assert blockers(repo, engine, "SMT-62") == []


def test_a_dependent_waits_until_its_dependency_is_merged_not_only_done(tmp_path):
    repo, config, engine = team_project(tmp_path)
    assert "SMT-62 is not merged into the story branch yet" in blockers(repo, engine, "SMT-63")[0]
    assert run_task(config, RUN, "SMT-62", TeamRunner(), engine=engine).ok
    assert len(blockers(repo, engine, "SMT-63")) == 1  # Done, committed, but not merged
    merge_attempt(config, RUN, "SMT-62", engine=engine)
    assert blockers(repo, engine, "SMT-63") == []
    assert s.task_states(repo, RUN, engine) == {"SMT-62": s.MERGED}


def test_a_failed_dependency_keeps_its_dependents_waiting(tmp_path):
    repo, config, engine = team_project(tmp_path, verify=(FAIL,))
    result = run_task(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    assert not result.ok
    assert s.task_states(repo, RUN, engine) == {"SMT-62": s.OTHER}
    assert "not merged" in blockers(repo, engine, "SMT-63")[0]


def unordered_with_shared_file(repo):
    """SMT-63 no longer depends on SMT-62, and both change src/a.py."""
    plan = load_plan(repo, RUN)
    plan["tasks"][1].update(depends_on=[], files=["src/a.py"])
    write_json_atomic(plan_path(repo, RUN), plan)


def test_two_tasks_that_share_a_file_do_not_run_together(tmp_path):
    repo, config, engine = team_project(tmp_path)
    unordered_with_shared_file(repo)
    assert blockers(repo, engine, "SMT-63") == []  # nothing runs yet
    build_attempt(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    (reason,) = blockers(repo, engine, "SMT-63")
    assert "SMT-62 is running or not merged yet and both change src/a.py" in reason
    assert blockers(repo, engine, "SMT-62") == []  # a task never waits for itself


def test_the_waiting_ends_when_the_other_task_is_merged(tmp_path):
    repo, config, engine = team_project(tmp_path)
    unordered_with_shared_file(repo)
    assert run_task(config, RUN, "SMT-62", TeamRunner(), engine=engine).ok
    assert len(blockers(repo, engine, "SMT-63")) == 1  # Done is not merged
    merge_attempt(config, RUN, "SMT-62", engine=engine)
    assert blockers(repo, engine, "SMT-63") == []


def test_files_of_unordered_tasks_that_do_not_overlap_never_wait(tmp_path):
    repo, config, engine = team_project(tmp_path)
    plan = load_plan(repo, RUN)
    plan["tasks"][1].update(depends_on=[], files=["src/other.py"])
    write_json_atomic(plan_path(repo, RUN), plan)
    build_attempt(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    assert blockers(repo, engine, "SMT-63") == []


def test_a_stopped_task_still_holds_its_files_but_a_cancelled_one_lets_go(tmp_path):
    repo, config, engine = team_project(tmp_path)
    unordered_with_shared_file(repo)
    assert build_attempt(config, RUN, "SMT-62", TeamRunner(), engine=engine).ok
    interrupt.settle_task(engine, repo, RUN, "SMT-62", tc.STOPPED, "tester", 1, force=True)
    (reason,) = blockers(repo, engine, "SMT-63")  # it will be continued: its files are taken
    assert "SMT-62 is running or not merged yet" in reason
    interrupt.settle_task(engine, repo, RUN, "SMT-62", tc.CANCELLED, "tester", 1, force=True)
    assert blockers(repo, engine, "SMT-63") == []  # cancelled for good: the files are free
