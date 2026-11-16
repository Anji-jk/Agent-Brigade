"""Retries: which attempt number comes next, and what the next Builder is told.

An attempt that Failed (the checks, the Tester or the Reviewer found a defect, or it could not be
merged) is not repaired in place. The next attempt is a fresh worktree from the story tip as it
is now, and its Builder gets the feedback of the failed attempt: the judge's, or the merge's.
A task has its first attempt and at most BRIGADE_MAX_RETRIES retries (.env); after that it is
Failed for good.
"""

from pathlib import Path

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories import merge_rows
from pipeline.stages.errors import BuildError
from pipeline.stages.stage_inputs import read_report, report_path

RETRYABLE = ("failed", "needs_review")


def previous_feedback(root: Path, run_id: str, key: str, number: int) -> str:
    """What attempt `number - 1` left for its successor: its merge feedback, else its judge's."""
    if number < 2:
        return ""
    for stage in ("merge", "judge"):
        report = read_report(report_path(root, run_id, stage, key, number - 1))
        if report and str(report.get("feedback") or "").strip():
            return str(report["feedback"])
    return ""


def next_attempt_number(engine: Engine, run_id: str, key: str, max_retries: int) -> int:
    """The number of the retry of `key`. BuildError says why there is none."""
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, run_id, key)
    if found is None:
        raise BuildError(f"{key} has no attempt yet in run {run_id}: start it with task.")
    _, attempt = found
    limit = 1 + max_retries
    if attempt.outcome == "done":
        raise BuildError(
            f"Attempt {attempt.number} of {key} is Done: merge it, there is nothing to retry."
        )
    if attempt.outcome not in RETRYABLE:
        raise BuildError(
            f"Attempt {attempt.number} of {key} is not finished ({attempt.outcome or 'running'}): "
            "judge it first."
        )
    if attempt.number >= limit:
        raise BuildError(
            f"{key} has used all {limit} attempts (the first and {max_retries} retries, "
            "BRIGADE_MAX_RETRIES in .env): it is Failed for good. The tasks that depend on it "
            "cannot start."
        )
    return attempt.number + 1
