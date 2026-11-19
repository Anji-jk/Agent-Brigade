"""A limit the agent hit (turns, time or dollars) is told apart from any other failure."""

import subprocess
from pathlib import Path

import pytest

from pipeline.runner.claude_runner import AgentError, AgentLimit, AgentRequest, ClaudeCliRunner
from tests.pipeline.runner.test_claude_runner import FakeRun, answer
from tests.pipeline.runner.test_stream_events import INIT, RESULT, FakePopen, FakeProcess, lines

SESSION = "11111111-2222-3333-4444-555555555555"


def asked(**more):
    return AgentRequest(
        agent="builder", prompt="Do it", cwd=Path("/repo"), session_id=SESSION, resume=False,
        timeout=30, **more,
    )  # fmt: skip


def hit(subtype, **more):
    return answer(is_error=True, subtype=subtype, result="", **more)


def test_the_turn_limit_is_a_limit_and_keeps_what_it_spent():
    run = FakeRun(stdout=hit("error_max_turns", total_cost_usd=2.14, num_turns=100))
    with pytest.raises(AgentLimit) as caught:
        ClaudeCliRunner("claude", run=run).run(asked(max_turns=100))
    assert caught.value.limit == "turns"
    assert "limit of 100 turns" in str(caught.value)
    assert caught.value.partial is not None
    assert (caught.value.partial.cost_usd, caught.value.partial.turns) == (2.14, 100)


def test_the_spending_cap_is_a_limit():
    run = FakeRun(stdout=hit("error_max_budget_usd", total_cost_usd=1.0))
    with pytest.raises(AgentLimit) as caught:
        ClaudeCliRunner("claude", run=run).run(asked(max_budget_usd=1.0))
    assert caught.value.limit == "budget" and caught.value.partial.cost_usd == 1.0


def test_a_limit_is_still_an_agent_error_for_every_caller_that_catches_one():
    run = FakeRun(stdout=hit("error_max_turns"))
    with pytest.raises(AgentError):
        ClaudeCliRunner("claude", run=run).run(asked(max_turns=5))


def test_any_other_failure_is_not_a_limit():
    run = FakeRun(stdout=answer(is_error=True, subtype="error_during_execution", result="boom"))
    with pytest.raises(AgentError) as caught:
        ClaudeCliRunner("claude", run=run).run(asked())
    assert not isinstance(caught.value, AgentLimit)


def test_running_out_of_time_is_a_limit_with_nothing_to_record():
    run = FakeRun(raises=subprocess.TimeoutExpired("claude", 30))
    with pytest.raises(AgentLimit) as caught:
        ClaudeCliRunner("claude", run=run).run(asked())
    assert caught.value.limit == "time" and caught.value.partial is None
    assert "did not finish within 30 seconds" in str(caught.value)


def test_running_out_of_time_in_a_stream_is_a_limit_too(tmp_path):
    popen = FakePopen(FakeProcess(lines(INIT), hang=True))
    runner = ClaudeCliRunner("claude", popen=popen, kill=popen.kill)
    with pytest.raises(AgentLimit) as caught:
        runner.run(asked(events_file=tmp_path / "builder.events.jsonl"))
    assert caught.value.limit == "time" and len(popen.killed) == 1


def test_a_limit_in_a_stream_keeps_what_it_spent(tmp_path):
    over = {**RESULT, "is_error": True, "subtype": "error_max_turns", "result": ""}
    popen = FakePopen(FakeProcess(lines(INIT, over)))
    runner = ClaudeCliRunner("claude", popen=popen, kill=popen.kill)
    with pytest.raises(AgentLimit) as caught:
        runner.run(asked(max_turns=3, events_file=tmp_path / "builder.events.jsonl"))
    assert caught.value.partial.cost_usd == 0.12 and caught.value.partial.turns == 3
