"""The Documenter: its message, its limits and what it may write."""

import pytest

from core.db import get_session
from core.db.models import AgentRun
from pipeline.documenting.doc_prompt import documenter_prompt
from pipeline.documenting.doc_requests import DOCUMENTER_TOOLS, documenter_request
from pipeline.documenting.doc_result import format_doc_result, write_doc_result
from pipeline.documenting.documenter_run import outside_the_list, run_documenter
from pipeline.documenting.facts import collect_facts
from pipeline.stages import builder_run as b
from pipeline.stages.stage_inputs import load_inputs
from tests.pipeline.stages.builder_setup import FakeRunner, build_project
from tests.pipeline.stages.stage_setup import RUN

REPORT = "**Wrote:** src/T1.py\n**Left out:** nothing\n**Not tested:** nothing"


@pytest.fixture
def world(tmp_path):
    repo, config, engine = build_project(tmp_path)
    b.build_attempt(config, RUN, "SMT-62", FakeRunner(), engine=engine)
    (load_inputs(config, RUN, "SMT-62", 1).worktree / "src").mkdir(exist_ok=True)
    facts = collect_facts(engine, repo, RUN)
    return repo, config, engine, facts


def documenter(world, runner):
    repo, config, engine, facts = world
    inputs = load_inputs(config, RUN, "SMT-62", 1)
    return run_documenter(engine, inputs, runner, facts)


def roles(engine):
    with get_session(engine) as session:
        return [(r.role, r.status) for r in session.query(AgentRun)]


def test_a_documenter_that_writes_a_listed_file_is_accepted(world):
    runner = FakeRunner(write={"src/T1.py": "# docs\n"}, text=REPORT)
    result = documenter(world, runner)
    assert result.ok and result.wrote == ["src/T1.py"] and result.outside == []
    assert result.report == REPORT and result.usage["cost_usd"] == 0.1234
    assert ("documenter", "done") in roles(world[2])


def test_a_file_outside_the_task_list_is_refused_and_named(world):
    runner = FakeRunner(write={"src/T1.py": "x", "README.md": "y"}, text=REPORT)
    result = documenter(world, runner)
    assert not result.ok and result.outside == ["README.md"]
    assert "does not list: README.md" in (result.error or "")


def test_an_agent_error_is_kept_and_its_row_is_closed(world):
    result = documenter(world, FakeRunner(error="out of turns"))
    assert not result.ok and result.error == "out of turns"
    assert [r for r in roles(world[2]) if r[0] == "documenter"] == [("documenter", "error")]


def test_an_empty_answer_is_asked_again_in_prose_not_json(world):
    runner = FakeRunner(text="   ")
    result = documenter(world, runner)
    assert "could not be used" in (result.error or "")
    assert len(runner.requests) == 2
    assert "Wrote, Left out, Not tested" in runner.requests[1].prompt
    assert "JSON" not in runner.requests[1].prompt


def test_the_request_has_no_shell_and_the_low_effort_limits(world):
    runner = FakeRunner(text=REPORT)
    documenter(world, runner)
    (request,) = runner.requests
    assert request.agent == "documenter" and request.tools == DOCUMENTER_TOOLS
    assert "Bash" not in request.tools and "PowerShell" not in request.tools
    assert (request.model, request.effort) == ("sonnet", "low")
    assert request.agent_file.name == "documenter.md" and request.agent_file.is_file()


def test_the_message_has_the_task_the_files_and_the_facts(world):
    _, config, _, facts = world
    task = load_inputs(config, RUN, "SMT-62", 1).task
    text = documenter_prompt(task, facts)
    assert "## Files you may write (no others)" in text and "- src/T1.py" in text
    assert "## Accept" in text and "- It works." in text
    assert f"Run {RUN}" in text and "Merged files:" in text
    assert "Feedback" not in text
    assert "Feedback from the Documentation Reviewer" in documenter_prompt(task, facts, "x")


def test_a_task_that_lists_no_file_allows_no_write():
    assert outside_the_list(["a.md"], []) == ["a.md"]
    assert outside_the_list(["docs\\a.md", "b.md"], ["./docs/a.md"]) == ["b.md"]


def test_the_result_is_saved_and_readable(world):
    repo = world[0]
    result = documenter(world, FakeRunner(write={"src/T1.py": "d"}, text=REPORT))
    path = write_doc_result(repo, result)
    assert path.name == "SMT-62-1.json" and path.parent.name == "docs"
    text = format_doc_result(result, path)
    assert "Wrote (1): src/T1.py" in text and "**Wrote:**" in text


def test_the_request_builder_keeps_the_worktree_and_the_session(world):
    _, config, _, _ = world
    inputs = load_inputs(config, RUN, "SMT-62", 1)
    request = documenter_request("p", inputs.worktree, inputs.root, "sid", resume=True)
    assert request.cwd == inputs.worktree and request.session_id == "sid" and request.resume
