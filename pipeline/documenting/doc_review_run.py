"""Run the Documentation Reviewer on the documents a Documenter wrote.

Order: code reads the documents; the Reviewer is asked whether each thing they claim has proof
in the measured facts or in the files; code reads the answer strictly and decides.
The Reviewer is read-only, and that it changed nothing is checked, not assumed. Its agent_runs
row has the role "reviewer"; its events file is named doc-reviewer.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine

from core.db import get_session
from core.db.models import AgentRun
from core.db.repositories import attempt_rows, judge_rows
from pipeline.documenting.doc_requests import doc_reviewer_request, limits
from pipeline.documenting.doc_review_prompt import doc_review_prompt, line_counts
from pipeline.documenting.doc_verdict import (
    DocVerdict,
    ReviewDecision,
    decide_review,
    parse_doc_review,
)
from pipeline.documenting.facts_model import StoryFacts
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages.agent_ask import ask_for_report, usage_of
from pipeline.stages.attempt_log import agent_events_path
from pipeline.stages.stage_inputs import Inputs
from pipeline.workspace.git import repository_state
from pipeline.workspace.snapshot import fingerprints

AGAIN = (
    "Your answer could not be used: {why} Answer again with only the JSON object described in "
    "your instructions, judging every claim with its file and line and every criterion."
)


@dataclass
class DocReview:
    decision: ReviewDecision
    verdict: DocVerdict | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None  # no usable answer: the work goes to a person

    @property
    def passed(self) -> bool:
        return self.error is None and self.decision.passed


def read_documents(inputs: Inputs, wrote: list[str]) -> dict[str, str]:
    """The text of each file the Documenter wrote, as it is in the worktree."""
    documents = {}
    for name in wrote:
        path = inputs.worktree / name
        if path.is_file():
            documents[name] = path.read_text(encoding="utf-8", errors="replace")
    return documents


def run_doc_reviewer(
    engine: Engine, inputs: Inputs, runner: AgentRunner, facts: StoryFacts, wrote: list[str]
) -> DocReview:
    documents = read_documents(inputs, wrote)
    chosen, session_id = limits("reviewer"), str(uuid.uuid4())
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, inputs.run_id, inputs.key, inputs.number)
        row = attempt_rows.start_agent_run(
            session, attempt, "reviewer", chosen["model"], chosen["effort"], session_id,
            datetime.now(UTC),
        )  # fmt: skip
        judge_rows.set_stage(session, sub, "doc-reviewer")
        row_id = row.id
    events = agent_events_path(
        inputs.root, inputs.run_id, inputs.key, inputs.number, "doc-reviewer"
    )
    request = doc_reviewer_request(
        doc_review_prompt(inputs.task, facts, documents),
        inputs.worktree, inputs.root, session_id, events_file=events,
    )  # fmt: skip
    lines, count = line_counts(documents), len(inputs.criteria)
    before = fingerprints(inputs.worktree), repository_state(inputs.root)
    asked = ask_for_report(
        runner, request, lambda text: parse_doc_review(text, count, lines), AGAIN
    )
    error = asked.error
    if before != (fingerprints(inputs.worktree), repository_state(inputs.root)):
        asked.report, error = None, "The Documentation Reviewer changed files, and it is read-only."
    with get_session(engine) as session:
        row = session.get(AgentRun, row_id)
        if row is not None:
            attempt_rows.finish_agent_run(
                session, row, asked.reply, error=error, now=datetime.now(UTC)
            )
    if asked.report is None:
        decision = ReviewDecision(False, [error or "no usable answer"])
        return DocReview(decision, None, usage_of(asked.reply), error)
    return DocReview(decide_review(asked.report), asked.report, usage_of(asked.reply))