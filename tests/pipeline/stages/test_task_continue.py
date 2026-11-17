"""Continue: a stopped attempt goes on in the same worktree, from the stage it had reached."""

import json

import pytest
from sqlalchemy import select

from core.db import get_session
from core.db.models import Attempt
from core.runs import run_directory
from pipeline.control import task_control as tc
from pipeline.stages import checkpoint, interrupt, task_run
from pipeline.stages.attempt_log import AttemptLog
from pipeline.stages.attempt_resume import RESUME_NOTE
from pipeline.stages.errors import BuildError
from pipeline.workspace import layout
from pipeline.workspace.worktrees import remove_worktree
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import TeamRunner, team_project
from tests.pipeline.stages.test_task_stop import KEY, AskingRunner, newest


def stop_at(role, tmp_path):
    repo, config, engine = team_project(tmp_path)
    with pytest.raises(interrupt.TaskInterrupted):
        task_run.run_task(config, RUN, KEY, AskingRunner(repo, role, tc.STOP), engine=engine)
    return repo, config, engine


def attempts(engine):
    with get_session(engine) as session:
        return [
            (a.number, a.outcome) for a in session.scalars(select(Attempt).order_by(Attempt.id))
        ]


def _steps(repo):
    path = AttemptLog(repo, RUN, KEY, 1).path
    return [json.loads(line)["step"] for line in path.read_text().splitlines()]


def test_a_task_stopped_at_the_builder_goes_on_in_the_same_worktree(tmp_path):
    repo, config, engine = stop_at("builder", tmp_path)
    worktree = layout.attempt_worktree(config.worktrees_dir, RUN, KEY, 1)
    (worktree / "src").mkdir(exist_ok=True)
    (worktree / "src" / "half.py").write_text("half = 1\n", encoding="utf-8")  # unfinished work
    tc.unsettle(run_directory(repo, RUN), KEY)
    runner = TeamRunner()
    done = task_run.run_task(config, RUN, KEY, runner, 1, engine, resume=True)
    assert done.ok
    assert (worktree / "src" / "half.py").exists()  # not thrown away, not started over
    builder = next(r for r in runner.requests if r.agent == "builder")
    assert RESUME_NOTE in builder.prompt
    assert attempts(engine) == [(1, "done")]  # the same attempt, no new row, no retry spent
    assert "worktree_reused" in _steps(repo) and "attempt_continued" in _steps(repo)


def test_a_task_stopped_in_the_tester_does_not_pay_for_the_builder_again(tmp_path):
    repo, config, engine = stop_at("tester", tmp_path)
    tc.unsettle(run_directory(repo, RUN), KEY)
    runner = TeamRunner()
    done = task_run.run_task(config, RUN, KEY, runner, 1, engine, resume=True)
    assert done.ok and done.built is None
    assert [r.agent for r in runner.requests] == ["tester", "reviewer"]
    assert "Builder: finished before the stop" in done.text
    assert attempts(engine) == [(1, "done")]
    assert newest(engine)[2] == "done"
    assert checkpoint.completed(repo, RUN, KEY, 1) == ["builder", "checks", "tester"]


def test_a_task_stopped_before_the_judge_runs_only_the_judge(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = AskingRunner(repo, "tester", tc.STOP, kill=False)
    with pytest.raises(interrupt.TaskInterrupted):
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    tc.unsettle(run_directory(repo, RUN), KEY)
    again = TeamRunner()
    done = task_run.run_task(config, RUN, KEY, again, 1, engine, resume=True)
    assert done.ok and [r.agent for r in again.requests] == ["reviewer"]


def test_the_row_is_running_again_while_it_goes_on(tmp_path):
    repo, config, engine = stop_at("reviewer", tmp_path)
    seen = []

    class Looking(TeamRunner):
        def run(self, request):
            seen.append(newest(engine)[:3])
            return super().run(request)

    task_run.run_task(config, RUN, KEY, Looking(), 1, engine, resume=True)
    assert seen == [("running", "reviewer", None)]  # the Reviewer sets its own stage


def test_a_continue_that_is_stopped_again_resumes_from_the_same_place(tmp_path):
    repo, config, engine = stop_at("tester", tmp_path)
    tc.unsettle(run_directory(repo, RUN), KEY)
    with pytest.raises(interrupt.TaskInterrupted) as again:
        task_run.run_task(
            config, RUN, KEY, AskingRunner(repo, "tester", tc.STOP), 1, engine, resume=True
        )
    assert again.value.stage == "tester" and attempts(engine) == [(1, "stopped")]


def test_a_continue_whose_worktree_is_gone_is_refused_before_anything_is_paid(tmp_path):
    repo, config, engine = stop_at("builder", tmp_path)
    remove_worktree(
        repo, layout.attempt_worktree(config.worktrees_dir, RUN, KEY, 1), discard_changes=True
    )
    tc.unsettle(run_directory(repo, RUN), KEY)
    runner = TeamRunner()
    with pytest.raises(BuildError, match="worktree is gone"):
        task_run.run_task(config, RUN, KEY, runner, 1, engine, resume=True)
    assert runner.requests == []
