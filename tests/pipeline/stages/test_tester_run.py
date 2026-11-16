import json

import pytest

from core.db import get_session
from core.db.models import AgentRun
from pipeline.runner.claude_runner import AgentRequest
from pipeline.stages import builder_run as b
from pipeline.stages import tester_report as tr
from pipeline.stages import tester_run as t
from tests.pipeline.stages.stage_setup import FAIL, OK, RUN, line
from tests.pipeline.stages.team_setup import (
    TeamRunner,
    answer_of_tester,
    built_and_checked,
    team_project,
)


def run(repo, config, engine, runner):
    built_and_checked(repo, config, engine, runner)
    return t.run_tester(config, RUN, "SMT-62", runner, engine=engine)


def agent_rows(engine):
    with get_session(engine) as session:
        return [(r.role, r.status, r.turns, r.cost) for r in session.query(AgentRun)]


def test_the_tester_is_skipped_when_the_task_has_no_place_for_tests(tmp_path):
    repo, config, engine = team_project(tmp_path, old_test=False)
    runner = TeamRunner()
    result = run(repo, config, engine, runner)
    assert result.skipped == "the task lists no test file and the project has no test files."
    assert not result.ran and result.ok
    assert runner.of("tester") == []
    assert [row[0] for row in agent_rows(engine)] == ["builder"]
    assert "Tester skipped: the task lists no test file" in tr.format_tester(result)


def test_a_script_in_a_test_folder_is_not_a_place_for_tests_and_the_skip_says_why(tmp_path):
    script = {"scripts/test/run-app.ps1": "Write-Host 'x'\n"}
    repo, config, engine = team_project(tmp_path, old_test=False, extra=script)
    result = run(repo, config, engine, TeamRunner())
    assert not result.ran and result.ok
    assert "scripts/test/run-app.ps1" in (result.skipped or "")


def test_a_task_that_lists_a_test_file_gets_a_tester_even_in_a_project_without_tests(tmp_path):
    repo, config, engine = team_project(
        tmp_path, old_test=False, files=("src/a.py", "tests/test_new.py")
    )
    assert run(repo, config, engine, TeamRunner()).ran


def test_the_tester_writes_tests_that_are_named_measured_and_run_with_the_verify_lines(tmp_path):
    repo, config, engine = team_project(tmp_path, verify=(OK,))
    runner = TeamRunner()
    result = run(repo, config, engine, runner)
    assert result.ran and result.ok and not result.problems
    assert result.wrote == ["tests/test_new.py"] and result.outside == []
    assert result.coverage == {"1": ["tests/test_new.py::test_new"]}
    assert [row["command"] for row in result.verify] == [OK]
    (request,) = runner.of("tester")
    assert isinstance(request, AgentRequest) and request.agent == "tester"
    assert request.cwd == tmp_path / "bw" / RUN / "SMT-62-1" and "1. It works." in request.prompt
    assert ("tester", "done", 3, 0.1) in agent_rows(engine)
    text = tr.format_tester(result, tr.write_tester_result(repo, result))
    assert "criterion 1: tests/test_new.py::test_new" in text and "ok     " in text
    saved = repo / ".agent-brigade" / "runs" / RUN / "test" / "SMT-62-1.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["wrote"] == ["tests/test_new.py"]


def test_the_verify_lines_run_after_the_tester_and_can_fail_on_its_tests(tmp_path):
    look = line("import sys; sys.exit(1 if 'assert 2' in open('tests/test_new.py').read() else 0)")
    repo, config, engine = team_project(tmp_path, verify=(look,))
    result = run(repo, config, engine, TeamRunner())
    assert [row["exit_code"] for row in result.verify] == [1] and result.ok


def test_a_write_outside_the_test_places_is_measured(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(tester={"tests/test_new.py": "x", "src/a.py": "x = 2\n", "notes.md": "n"})
    result = run(repo, config, engine, runner)
    assert result.outside == ["notes.md", "src/a.py"] and result.problems


def test_a_removed_assertion_in_an_existing_test_is_measured(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(
        tester={"tests/test_old.py": "def test_old():\n    pass\n", "tests/test_new.py": "x"}
    )
    assert run(repo, config, engine, runner).weakened == ["tests/test_old.py"]


def test_named_tests_must_exist_in_a_test_place_and_be_the_testers_own(tmp_path):
    repo, config, engine = team_project(tmp_path)
    said = answer_of_tester({1: ["tests/test_old.py::test_old", "src/a.py::t", "tests/ghost.py"]})
    result = run(repo, config, engine, TeamRunner(tester_text=said))
    assert len(result.invalid) == 3 and "did not write" in result.invalid[0]
    assert "not in a test location" in result.invalid[1]


def test_criteria_without_a_test_or_a_reason_and_no_tests_at_all_are_measured(tmp_path):
    repo, config, engine = team_project(tmp_path, criteria=("A", "B", "C"))
    said = answer_of_tester({1: ["tests/test_new.py"]}, uncovered={3: "visual only"})
    result = run(repo, config, engine, TeamRunner(tester_text=said))
    assert result.unnamed == [2] and result.uncovered == {"3": "visual only"}
    assert not run_none(tmp_path / "two").no_tests  # a reason for every criterion is enough
    listed = run_none(tmp_path / "three", files=("src/a.py", "tests/test_new.py"))
    assert listed.no_tests  # but not when the task itself lists a test file
    nothing = run_none(tmp_path / "four", uncovered={})
    assert nothing.no_tests and nothing.unnamed == [1]


def run_none(path, files=("src/a.py",), uncovered=None):
    repo, config, engine = team_project(path, files=files)
    reasons = {1: "cannot"} if uncovered is None else uncovered
    return run(repo, config, engine, TeamRunner(tester_text=answer_of_tester({}, reasons)))


def test_an_unusable_report_is_asked_for_again_in_the_same_session(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(tester_text=["no json here", answer_of_tester()])
    result = run(repo, config, engine, runner)
    first, second = runner.of("tester")
    assert result.ok and second.resume and second.session_id == first.session_id
    assert "could not be used" in second.prompt
    assert result.usage["turns"] == 6 and result.usage["cost_usd"] == pytest.approx(0.2)
    assert [r[0] for r in agent_rows(engine)].count("tester") == 1  # one row, usage added up


def test_two_unusable_reports_or_a_crash_stop_the_tester_and_skip_the_verify_lines(tmp_path):
    repo, config, engine = team_project(tmp_path)
    result = run(repo, config, engine, TeamRunner(tester_text=["nope", "still nope"]))
    assert not result.ok and "even when asked again" in str(result.error)
    assert result.verify == []
    repo, config, engine = team_project(tmp_path / "two")
    result = run(repo, config, engine, TeamRunner(errors={"tester": "it ran out"}))
    assert result.error == "it ran out" and result.verify == []
    assert ("tester", "error", None, None) in agent_rows(engine)


def test_a_blocking_check_failure_skips_the_tester_and_a_missing_check_is_refused(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(builder={})
    result = run(repo, config, engine, runner)
    assert "a blocking check failed" in str(result.skipped) and runner.of("tester") == []
    repo, config, engine = team_project(tmp_path / "two")
    b.build_attempt(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    with pytest.raises(b.BuildError, match="run check first"):
        t.run_tester(config, RUN, "SMT-62", TeamRunner(), engine=engine)


def test_a_failing_verify_line_is_a_fact_not_an_error_here(tmp_path):
    repo, config, engine = team_project(tmp_path, verify=(FAIL,))
    result = run(repo, config, engine, TeamRunner())
    assert result.ok and result.verify[0]["exit_code"] == 3
