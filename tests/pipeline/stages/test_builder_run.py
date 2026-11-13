import json

import pytest

from core.db import get_session
from core.db.models import AgentRun, Attempt, SubTask
from pipeline.runner.claude_runner import AgentRequest
from pipeline.stages import builder_run as b
from pipeline.stages.builder_report import format_build, write_build_report
from pipeline.stages.builder_rows import format_rows
from pipeline.stages.prepare import PrepareError
from tests.pipeline.stages.builder_setup import FakeRunner, build_project
from tests.pipeline.stages.stage_setup import FAIL, MAKE_FILE, OK, RUN
from tests.pipeline.workspace.repo import git


def rows(engine):
    with get_session(engine) as s:
        return (
            s.query(SubTask).all(),
            s.query(Attempt).all(),
            s.query(AgentRun).all(),
        )


def test_a_builder_attempt_runs_in_its_worktree_and_is_recorded(tmp_path):
    repo, config, engine = build_project(tmp_path, setup=[MAKE_FILE], checks=[OK])
    runner = FakeRunner(write={"new.txt": "hello"})
    result = b.build_attempt(config, RUN, "SMT-62", runner, engine=engine)
    assert result.ok and result.changed and "new.txt" in result.changed
    (request,) = runner.requests
    assert isinstance(request, AgentRequest)
    assert request.cwd == tmp_path / "bw" / RUN / "SMT-62-1" and request.agent == "builder"
    assert request.model == "sonnet" and request.max_turns and request.max_budget_usd
    assert "SMT-62" in request.prompt and "Do T1" in request.prompt
    sub_tasks, attempts, agent_runs = rows(engine)
    assert [(s.key, s.status, s.current_stage, s.size) for s in sub_tasks] == [
        ("SMT-62", "running", "builder", "small")
    ]
    (attempt,) = attempts
    assert attempt.number == 1 and attempt.outcome == "built" and attempt.ended_at
    assert attempt.branch == f"agent-attempt/{RUN}/SMT-62-1"
    (run,) = agent_runs
    assert run.role == "builder" and run.status == "done" and run.session_id == request.session_id
    assert (run.turns, run.cost, run.duration_s) == (4, 0.1234, 5)
    assert (run.input_tokens, run.output_tokens, run.cache_tokens) == (100, 50, 10)
    assert run.model_requested == "sonnet" and run.model_used == "claude-sonnet"
    assert git(repo, "status", "--porcelain") == ""  # the project's own folder is untouched


def test_the_dependency_is_recorded_by_jira_key(tmp_path):
    _, config, engine = build_project(tmp_path)
    b.build_attempt(config, RUN, "SMT-63", FakeRunner(), engine=engine)
    (sub_task,) = rows(engine)[0]
    assert sub_task.key == "SMT-63" and sub_task.depends_on == "SMT-62"


def test_the_report_file_and_text_say_what_happened(tmp_path):
    repo, config, engine = build_project(tmp_path)
    result = b.build_attempt(config, RUN, "SMT-62", FakeRunner(write={"a.txt": "x"}), engine=engine)
    path = write_build_report(repo, result)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "SMT-62-1.json" and saved["ok"] is True
    assert saved["usage"]["cost_usd"] == 0.1234 and saved["changed"] == ["a.txt"]
    text = format_build(result, path)
    assert "Used:      4 turns, $0.1234, 5.2s" in text and "a.txt" in text
    assert "Built. Look at the worktree" in text


def test_a_failing_setup_means_no_builder_and_an_error_row(tmp_path):
    _, config, engine = build_project(tmp_path, setup=[FAIL])
    runner = FakeRunner()
    result = b.build_attempt(config, RUN, "SMT-62", runner, engine=engine)
    assert result.error and "setup failed" in result.error and runner.requests == []
    (sub_task,), (attempt,), agent_runs = rows(engine)
    assert sub_task.status == "error" and attempt.outcome == "error" and agent_runs == []
    assert "Stopped: setup failed" in format_build(result)


def test_an_agent_error_is_recorded_not_raised(tmp_path):
    _, config, engine = build_project(tmp_path)
    result = b.build_attempt(config, RUN, "SMT-62", FakeRunner(error="it ran out"), engine=engine)
    assert result.error == "it ran out" and result.usage == {}
    (sub_task,), (attempt,), (run,) = rows(engine)
    assert (sub_task.status, attempt.reason, run.status) == ("error", "it ran out", "error")
    assert run.exit_reason == "it ran out"


def test_a_change_to_the_projects_own_folder_is_an_error(tmp_path):
    repo, config, engine = build_project(tmp_path)

    class Sneaky(FakeRunner):
        def run(self, request):
            (repo / "oops.txt").write_text("x", encoding="utf-8")
            return super().run(request)

    result = b.build_attempt(config, RUN, "SMT-62", Sneaky(), engine=engine)
    assert result.error and "project's own folder changed" in result.error


@pytest.mark.parametrize(
    ("key", "approve", "board", "message"),
    [
        ("SMT-99", True, ("SMT-62",), "SMT-99 is not a task"),
        ("SMT-62", False, ("SMT-62",), "not an approved run in the database"),
        ("SMT-62", True, (), "press Sync"),
    ],
)
def test_refusals_happen_before_anything_is_made(tmp_path, key, approve, board, message):
    _, config, engine = build_project(tmp_path, approve=approve, board=board, prepared=False)
    with pytest.raises(b.BuildError, match=message):
        b.build_attempt(config, RUN, key, FakeRunner(), engine=engine)
    assert not (tmp_path / "bw").exists()


def test_the_run_must_be_prepared_first(tmp_path):
    _, config, engine = build_project(tmp_path, prepared=False)
    with pytest.raises(PrepareError, match="prepare the run first"):
        b.build_attempt(config, RUN, "SMT-62", FakeRunner(), engine=engine)


def test_the_rows_command_text_shows_what_was_written(tmp_path):
    _, config, engine = build_project(tmp_path)
    b.build_attempt(config, RUN, "SMT-62", FakeRunner(), engine=engine)
    text = format_rows(engine, RUN)
    assert "sub_tasks   #1 SMT-62  status=running stage=builder size=small" in text
    assert "attempts    #1 number=1 outcome=built" in text
    assert (
        "agent_runs  #1 builder status=done model=claude-sonnet effort=low turns=4 cost=0.1234"
        in text
    )
    assert "tokens=100/50/10" in text
    assert "not in the database" in format_rows(engine, "SMT-1-20260101-aaaa")
