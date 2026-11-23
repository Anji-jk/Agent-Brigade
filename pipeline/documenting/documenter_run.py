"""Run the Documenter on the worktree of a documentation task's attempt.

The Documenter takes the Builder's place for a documentation task. It may write only the files
the plan lists for the task. Claude Code cannot be told that, so what it wrote is measured by
fingerprinting the worktree before and after (as for the Tester): a file outside the list, or a
change in the project's own folder, is an error and nothing is committed. Its agent_runs row is
recorded with the role "documenter".
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Engine

from core.db import get_session
from core.db.models import AgentRun
from core.db.repositories import attempt_rows, judge_rows
from pipeline.checks.agent_reports import ReportError
from pipeline.documenting.doc_prompt import documenter_prompt
from pipeline.documenting.doc_requests import documenter_request, limits
from pipeline.documenting.doc_result import DocResult
from pipeline.documenting.facts_model import StoryFacts
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages.agent_ask import ask_for_report, usage_of
from pipeline.stages.attempt_log import agent_events_path
from pipeline.stages.stage_inputs import Inputs
from pipeline.workspace.git import repository_state
from pipeline.workspace.snapshot import fingerprints, written_between

AGAIN = (
    "Your answer could not be used: {why} Answer again with only the short report described in "
    "your instructions (Wrote, Left out, Not tested)."
)


def _text(answer: object) -> str:
    """The Documenter answers in prose; an empty answer is unusable."""
    if not isinstance(answer, str) or not answer.strip():
        raise ReportError("The Documenter's answer was empty.")
    return answer.strip()


def outside_the_list(wrote: list[str], allowed: list[str]) -> list[str]:
    """Paths written that the task's Files do not list (compared with / separators)."""
    listed = {path.replace("\\", "/").removeprefix("./") for path in allowed}
    return [path for path in wrote if path.replace("\\", "/") not in listed]


def run_documenter(
    engine: Engine, inputs: Inputs, runner: AgentRunner, facts: StoryFacts, feedback: str = ""
) -> DocResult:
    """Ask the Documenter once (with one repeat if the answer is empty). Never commits."""
    result = DocResult(inputs.run_id, inputs.key, inputs.number, limits())
    session_id = str(uuid.uuid4())
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, inputs.run_id, inputs.key, inputs.number)
        row = attempt_rows.start_agent_run(
            session, attempt, "documenter", result.limits["model"], result.limits["effort"],
            session_id, datetime.now(UTC),
        )  # fmt: skip
        judge_rows.set_stage(session, sub, "documenter")
        row_id = row.id
    events = agent_events_path(inputs.root, inputs.run_id, inputs.key, inputs.number, "documenter")
    request = documenter_request(
        documenter_prompt(inputs.task, facts, feedback), inputs.worktree, inputs.root, session_id,
        events_file=events,
    )  # fmt: skip
    before, project = fingerprints(inputs.worktree), repository_state(inputs.root)
    asked = ask_for_report(runner, request, _text, AGAIN)
    result.wrote = written_between(before, fingerprints(inputs.worktree))
    result.outside = outside_the_list(result.wrote, inputs.task.get("files", []))
    result.report = asked.report or ""
    result.error = asked.error
    if repository_state(inputs.root) != project:
        result.error = "The project's own folder changed while the Documenter ran."
    elif result.outside and result.error is None:
        result.error = "The Documenter wrote files the task does not list: " + ", ".join(
            result.outside
        )
    result.usage = usage_of(asked.reply)
    with get_session(engine) as session:
        row = session.get(AgentRun, row_id)
        if row is not None:
            attempt_rows.finish_agent_run(
                session, row, asked.reply, error=result.error, now=datetime.now(UTC)
            )
    return result
