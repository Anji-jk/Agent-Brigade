import json

import pytest

from pipeline.stages import __main__ as cli
from pipeline.stages import task_run
from tests.pipeline.stages.stage_setup import FAIL, OK, RUN
from tests.pipeline.stages.team_setup import TeamRunner, answer_of_reviewer, team_project
from tests.pipeline.workspace.repo import git


@pytest.fixture
def use(monkeypatch):
    """Point the command line at a test project and its database."""

    def point(config, engine):
        monkeypatch.setattr(cli, "get_settings", lambda: config)
        monkeypatch.setattr(cli, "get_engine", lambda: engine)
        monkeypatch.setattr("core.db.get_engine", lambda: engine)

    return point


def test_task_runs_every_stage_in_order_and_commits(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner()
    done = task_run.run_task(config, RUN, "SMT-62", runner, engine=engine)
    assert done.ok and [r.agent for r in runner.requests] == ["builder", "tester", "reviewer"]
    order = [
        "Attempt 1 of SMT-62",
        "Checks of attempt",
        "Tester of attempt",
        "Decision for attempt",
    ]
    assert [done.text.index(x) for x in order] == sorted(done.text.index(x) for x in order)
    assert "DONE" in done.text and "Committed: " in done.text
    folder = repo / ".agent-brigade" / "runs" / RUN
    for stage in ("build", "checks", "test", "judge"):
        assert (folder / stage / "SMT-62-1.json").is_file()
    saved = json.loads((folder / "judge" / "SMT-62-1.json").read_text(encoding="utf-8"))
    assert saved["outcome"] == "done" and saved["commit"] == (done.judged and done.judged.commit)


def test_a_builder_that_stops_ends_the_task_before_anything_else_is_paid(tmp_path):
    _, config, engine = team_project(tmp_path)
    runner = TeamRunner(errors={"builder": "it ran out"})
    done = task_run.run_task(config, RUN, "SMT-62", runner, engine=engine)
    assert not done.ok and done.judged is None and "Stopped: it ran out" in done.text
    assert [r.agent for r in runner.requests] == ["builder"]


def test_the_command_line_exit_codes_follow_the_decision(tmp_path, use, capsys):
    repo, config, engine = team_project(tmp_path, verify=(OK,))
    use(config, engine)
    assert cli.main(["task", RUN, "SMT-62"], TeamRunner()) == 0
    out = capsys.readouterr().out
    assert "DONE" in out and "Tester:" in out
    assert cli.main(["rows", RUN]) == 0
    rows = capsys.readouterr().out
    assert "outcome=done" in rows and "commit=" in rows and "tester status=done" in rows
    assert "reviewer status=done" in rows
    repo, config, engine = team_project(tmp_path / "bad", verify=(FAIL,))
    use(config, engine)
    assert cli.main(["task", RUN, "SMT-62"], TeamRunner()) == 2
    assert "FAILED" in capsys.readouterr().out


def test_test_and_judge_can_be_run_one_after_the_other_from_the_command_line(tmp_path, use, capsys):
    repo, config, engine = team_project(tmp_path)
    use(config, engine)
    runner = TeamRunner(reviewer_text=answer_of_reviewer((False,), problems=("wrong",)))
    assert cli.main(["build", RUN, "SMT-62"], runner) == 0
    assert cli.main(["check", RUN, "SMT-62"], runner) == 0
    assert cli.main(["test", RUN, "SMT-62"], runner) == 0
    assert "criterion 1: tests/test_new.py::test_new" in capsys.readouterr().out
    assert cli.main(["judge", RUN, "SMT-62"], runner) == 2
    out = capsys.readouterr().out
    assert (
        "FAILED" in out and "NOT MET 1. It works." in out and "Feedback for the next Builder" in out
    )
    assert git(tmp_path / "bw" / RUN / "SMT-62-1", "log", "--oneline").count("\n") == 1


def test_judge_before_check_is_refused_with_the_command_to_run(tmp_path, use, capsys):
    _, config, engine = team_project(tmp_path)
    use(config, engine)
    assert cli.main(["build", RUN, "SMT-62"], TeamRunner()) == 0
    assert cli.main(["judge", RUN, "SMT-62"], TeamRunner()) == 1
    assert "run check first" in capsys.readouterr().err
