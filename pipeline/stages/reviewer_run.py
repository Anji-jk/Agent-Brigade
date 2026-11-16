"""Run the Reviewer on one attempt: a read-only agent that judges the change criterion by criterion.

It is given a message built by code and cannot edit, run or commit anything. That it did not
change the worktree or the project is checked, not assumed. Its agent_runs row is recorded.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Engine

from core.db import get_session
from core.db.models import AgentRun
from core.db.repositories import attempt_rows, judge_rows
from pipeline.checks.agent_reports import parse_reviewer
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages.agent_ask import Asked, ask_for_report
from pipeline.stages.agent_requests import limits, reviewer_request
from pipeline.stages.attempt_log import agent_events_path
from pipeline.stages.stage_inputs import Inputs
from pipeline.workspace.git import repository_state
from pipeline.workspace.snapshot import fingerprints


def run_reviewer(engine: Engine, inputs: Inputs, runner: AgentRunner, prompt: str) -> Asked:
    """Ask the Reviewer. The answer has `.report` or `.error`; the usage is on `.reply`."""
    chosen, session_id = limits(inputs.task, "reviewer"), str(uuid.uuid4())
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, inputs.run_id, inputs.key, inputs.number)
        row = attempt_rows.start_agent_run(
            session, attempt, "reviewer", chosen["model"], chosen["effort"], session_id,
            datetime.now(UTC),
        )  # fmt: skip
        judge_rows.set_stage(session, sub, "reviewer")
        row_id = row.id
    events = agent_events_path(inputs.root, inputs.run_id, inputs.key, inputs.number, "reviewer")
    request = reviewer_request(
        inputs.task, prompt, inputs.worktree, inputs.root, session_id, events_file=events
    )
    before = fingerprints(inputs.worktree), repository_state(inputs.root)
    count = len(inputs.criteria)
    asked = ask_for_report(runner, request, lambda text: parse_reviewer(text, count))
    if before != (fingerprints(inputs.worktree), repository_state(inputs.root)):
        asked.report, asked.error = None, "The Reviewer changed files, and it is read-only."
    with get_session(engine) as session:
        row = session.get(AgentRun, row_id)
        if row is not None:
            attempt_rows.finish_agent_run(
                session, row, asked.reply, error=asked.error, now=datetime.now(UTC)
            )
    return asked
