"""The Documentation Reviewer run: a read-only agent and a strict decision."""

import json

import pytest

from core.db import get_session
from core.db.models import AgentRun
from pipeline.documenting.doc_review_run import run_doc_reviewer
from pipeline.documenting.facts import collect_facts
from pipeline.stages import builder_run as b
from pipeline.stages.stage_inputs import load_inputs
from tests.pipeline.stages.builder_setup import FakeRunner, build_project
from tests.pipeline.stages.stage_setup import RUN

GOOD_DOC = "The toggle saves the choice.\nIt edits src/T1.py.\n"


def reply(claims=None, **changes):
    data = {
        "verdict": "pass",
        "claims": claims
        or [{"file": "src/T1.py", "line": 1, "claim": "saves", "status": "supported",
             "evidence": "facts"}],
        "criteria": [{"criterion": 1, "met": True, "evidence": "line 1"}],
        "problems": [],
    }  # fmt: skip
    data.update(changes)
    return json.dumps(data)


@pytest.fixture
def world(tmp_path):
    repo, config, engine = build_project(tmp_path)
    b.build_attempt(config, RUN, "SMT-62", FakeRunner(), engine=engine)
    inputs = load_inputs(config, RUN, "SMT-62", 1)
    (inputs.worktree / "src").mkdir(exist_ok=True)
    (inputs.worktree / "src" / "T1.py").write_text(GOOD_DOC, encoding="utf-8")
    return inputs, engine, collect_facts(engine, repo, RUN)


def review(world, runner):
    inputs, engine, facts = world
    return run_doc_reviewer(engine, inputs, runner, facts, ["src/T1.py"])


def test_a_clean_document_with_all_claims_supported_passes(world):
    runner = FakeRunner(text=reply())
    result = review(world, runner)
    assert result.passed and result.usage["cost_usd"] == 0.1234
    with get_session(world[1]) as session:
        assert ("reviewer", "done") in [(r.role, r.status) for r in session.query(AgentRun)]


def test_the_reviewer_can_read_but_not_edit_or_run(world):
    runner = FakeRunner(text=reply())
    review(world, runner)
    (request,) = runner.requests
    assert request.agent == "doc-reviewer" and request.tools == ("Read", "Grep", "Glob")
    assert request.permission_mode == "dontAsk" and request.agent_file.is_file()
    assert (request.model, request.effort) == ("haiku", "low")


def test_the_message_has_numbered_lines_and_the_facts(world):
    runner = FakeRunner(text=reply())
    review(world, runner)
    prompt = runner.requests[0].prompt
    assert "   1| The toggle saves the choice." in prompt and "### src/T1.py (2 lines)" in prompt
    assert f"Run {RUN}" in prompt and "free check" not in prompt
    assert "1. It works." in prompt


def test_no_code_check_of_paths_or_amounts_overrules_the_reviewer(world):
    inputs, engine, facts = world
    text = "It edits src/other.py and cost $99 over 12 tasks.\n"
    (inputs.worktree / "src" / "T1.py").write_text(text, encoding="utf-8")
    result = review(world, FakeRunner(text=reply()))
    assert result.passed and result.decision.problems == []


def test_an_unsupported_claim_fails_and_its_line_is_named(world):
    bad = [{"file": "src/T1.py", "line": 2, "claim": "faster", "status": "unsupported",
            "evidence": "no fact"}]  # fmt: skip
    result = review(world, FakeRunner(text=reply(bad, verdict="fail")))
    assert not result.passed
    assert result.decision.problems == ["src/T1.py line 2 is unsupported: faster (no fact)"]


def test_an_answer_that_cannot_be_used_twice_is_an_error_not_a_pass(world):
    runner = FakeRunner(text="no json here")
    result = review(world, runner)
    assert not result.passed and result.verdict is None
    assert "even when asked again" in (result.error or "")
    assert len(runner.requests) == 2 and "every claim with its file" in runner.requests[1].prompt


def test_a_reviewer_that_edits_a_file_is_an_error(world):
    result = review(world, FakeRunner(text=reply(), write={"src/T1.py": "tampered\n"}))
    assert not result.passed and "read-only" in (result.error or "")


def test_a_reviewer_that_fails_the_run_keeps_the_cost(world):
    result = review(world, FakeRunner(error="stopped"))
    assert result.error == "stopped" and not result.passed
