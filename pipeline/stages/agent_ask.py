"""Ask an agent for its JSON report, and once more if the answer cannot be used.

An answer that is not the report (no JSON, a skipped criterion) is refused with the reason and
the agent is asked again in the same session, which still holds what it read. If the second
answer is also unusable the attempt is not guessed at: the caller gets an error and the work
goes to a person (Needs review). The usage of both answers is added up.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from pipeline.checks.agent_reports import ReportError
from pipeline.runner.claude_runner import (
    AgentError,
    AgentLimit,
    AgentReply,
    AgentRequest,
    AgentRunner,
)

AGAIN = (
    "Your answer could not be used: {why} Answer again with only the JSON object described in "
    "your instructions, with every acceptance criterion accounted for."
)


@dataclass
class Asked:
    report: Any | None
    reply: AgentReply | None
    error: str | None


def usage_of(reply: AgentReply | None) -> dict[str, Any]:
    if reply is None:
        return {}
    seconds = None if reply.duration_ms is None else round(reply.duration_ms / 1000, 1)
    return {
        "session_id": reply.session_id,
        "cost_usd": reply.cost_usd,
        "turns": reply.turns,
        "seconds": seconds,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "cache_tokens": reply.cache_tokens,
        "model_used": reply.model_used,
    }


def _sum(first: float | int | None, second: float | int | None) -> float | int | None:
    return second if first is None else first if second is None else first + second


def _added(first: AgentReply, second: AgentReply) -> AgentReply:
    return replace(
        second,
        cost_usd=_sum(first.cost_usd, second.cost_usd),
        turns=_sum(first.turns, second.turns),
        duration_ms=_sum(first.duration_ms, second.duration_ms),
        input_tokens=_sum(first.input_tokens, second.input_tokens),
        output_tokens=_sum(first.output_tokens, second.output_tokens),
        cache_tokens=_sum(first.cache_tokens, second.cache_tokens),
    )


def _spent(error: AgentError) -> AgentReply | None:
    """What an agent that ran into a limit had used up, so its cost is not lost."""
    return error.partial if isinstance(error, AgentLimit) else None


def ask_for_report(
    runner: AgentRunner, request: AgentRequest, parse: Callable[[str], Any], again: str = AGAIN
) -> Asked:
    """Run `request`; `parse` raises ReportError for an unusable answer. One more try.

    `again` is what the second message says; it must contain {why}."""
    try:
        reply = runner.run(request)
    except AgentError as exc:
        return Asked(None, _spent(exc), str(exc))
    try:
        return Asked(parse(reply.text), reply, None)
    except ReportError as exc:
        why = str(exc)
    retry = replace(
        request, resume=True, session_id=reply.session_id or request.session_id,
        prompt=again.format(why=why),
    )  # fmt: skip
    try:
        second = runner.run(retry)
    except AgentError as exc:
        spent = _spent(exc)
        return Asked(None, _added(reply, spent) if spent else reply, str(exc))
    reply = _added(reply, second)
    try:
        return Asked(parse(second.text), reply, None)
    except ReportError as exc:
        return Asked(None, reply, f"The answer could not be used, even when asked again: {exc}")
