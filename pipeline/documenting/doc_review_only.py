"""Ask only the Documentation Reviewer about an attempt, as its files are now.

For trying the Reviewer on a document someone changed by hand (a false sentence put in on purpose,
say). It records the Reviewer's cost as an agent run, but it commits nothing, changes no outcome,
writes no report and puts the task's stage word back (a merged task still says merged).
"""

from dataclasses import dataclass

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories import judge_rows, merge_rows
from core.settings import Settings
from pipeline.documenting.doc_decision import decide_doc_task
from pipeline.documenting.doc_task_run import review_attempt
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages.errors import BuildError

WORDS = {"done": "DONE", "failed": "FAILED", "needs_review": "NEEDS REVIEW", "retry": "FAILED"}


@dataclass
class ReviewOnly:
    status: str  # done | failed | needs_review
    text: str


def _newest(engine: Engine, run_id: str, key: str) -> int:
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, run_id, key)
        if found is None:
            raise BuildError(f"{key} has no attempt in run {run_id}: run the task first.")
        return found[1].number


def _stage(
    engine: Engine, run_id: str, key: str, number: int, put: str | None = None
) -> str | None:
    """The task's stage word; with `put`, set it back (the Reviewer overwrites it as it starts)."""
    with get_session(engine) as session:
        sub, _ = judge_rows.rows_of_attempt(session, run_id, key, number)
        before = sub.current_stage
        if put is not None:
            judge_rows.set_stage(session, sub, put)
        return before


def review_only(
    settings: Settings, run_id: str, key: str, runner: AgentRunner, number: int | None = None,
    *, engine: Engine,
) -> ReviewOnly:  # fmt: skip
    """The Reviewer's verdict on attempt `number` (default the newest) of `key`, as it stands."""
    number = number or _newest(engine, run_id, key)
    stage = _stage(engine, run_id, key, number)
    try:
        failures, defects, review, _ = review_attempt(settings, engine, runner, run_id, key, number)
    finally:
        if stage is not None:
            _stage(engine, run_id, key, number, put=stage)
    decision = decide_doc_task(
        documenter_error=None, check_failures=failures, verify_defects=defects, review=review,
        last_round=True,
    )  # fmt: skip
    status = "failed" if decision.status == "retry" else decision.status
    lines = [f"Documentation Reviewer only, attempt {number} of {key} in run {run_id}"]
    lines.append(WORDS[status])
    lines += [f"- {reason}" for reason in decision.reasons]
    if review is not None and review.usage:
        use = review.usage
        lines.append(f"Used: {use.get('turns')} turns, ${use.get('cost_usd') or 0:.4f}")
    lines.append("Nothing was committed or recorded as the task's outcome.")
    return ReviewOnly(status, "\n".join(lines))