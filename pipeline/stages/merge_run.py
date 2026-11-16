"""Merge one Done attempt into the story branch. No agent runs and nothing is spent.

merge_attempt   take the merge lock, then either fast-forward the story branch to the attempt's
                commit (its tip has not moved since the attempt started: the checks already ran on
                exactly this code) or make a real merge, check the combined code, and only commit
                it when those checks pass. A conflict, or a check that fails on the merged code,
                aborts the merge: the story branch is exactly as it was, and the attempt becomes
                Failed with feedback for the retry.

The story branch only ever moves to a state that was checked. The merge happens in the story
worktree, so the project's own folder and checked-out branch are never touched.
"""

from datetime import UTC, datetime

from sqlalchemy import Engine

from core.db import get_session, init_db
from core.db.repositories import judge_rows, merge_rows
from core.db.repositories.attempt_rows import BuildRecordError
from core.runs import run_directory
from core.settings import Settings
from pipeline.stages.baseline import read_baseline
from pipeline.stages.errors import BuildError
from pipeline.stages.merge_checks import check_lines, failure_text, run_checks
from pipeline.stages.merge_report import FAILED, MERGED, MergeResult
from pipeline.stages.prepare import approved_plan, project_root
from pipeline.stages.stage_inputs import find_task
from pipeline.workspace import layout
from pipeline.workspace.git import head_commit
from pipeline.workspace.lock import LockError, merge_lock
from pipeline.workspace.merge import (
    MergeConflict,
    abort_merge,
    begin_merge,
    fast_forward,
    finish_merge,
    is_ancestor,
    tracked_changes,
)

SUBJECT_CHARS = 120


def _pick(engine: Engine, run_id: str, key: str, number: int | None) -> tuple[int, str]:
    """(the attempt number, its commit). BuildError unless it is a Done attempt with a commit."""
    with get_session(engine) as session:
        if number is None:
            found = merge_rows.newest_attempt(session, run_id, key)
            if found is None:
                raise BuildError(f"{key} has no attempt in run {run_id}: build it first.")
            attempt = found[1]
        else:
            try:
                attempt = judge_rows.rows_of_attempt(session, run_id, key, number)[1]
            except BuildRecordError as exc:
                raise BuildError(str(exc)) from None
        outcome, commit, num = attempt.outcome, attempt.commit_sha, attempt.number
    if outcome != "done" or not commit:
        raise BuildError(
            f"Attempt {num} of {key} is {outcome or 'not finished'}, not Done: "
            "only a Done attempt, committed by judge, is merged."
        )
    return num, commit


def merge_feedback(number: int, reasons: list[str]) -> str:
    lines = [
        f"Attempt {number} of this task was Done, but it could not be merged into the story branch."
    ]
    lines += ["What was found:", *[f"- {reason}" for reason in reasons]]
    lines += [
        "",
        "This is a new attempt on the story branch as it is now: the work merged since is already "
        "here. Make the change again so that it fits with it, and make sure these problems do "
        "not occur.",
    ]
    return "\n".join(lines)


def _fail(result: MergeResult, reasons: list[str]) -> None:
    result.outcome, result.reasons = FAILED, reasons
    result.tip_after = result.tip_before
    result.feedback = merge_feedback(result.number, reasons)


def _merge_locked(
    settings: Settings, result: MergeResult, plan: dict, task: dict, story_worktree
) -> None:
    root = project_root(settings)
    dirty = tracked_changes(story_worktree)
    if dirty:
        raise BuildError(
            f"The story worktree has {len(dirty)} uncommitted change(s) (first: {dirty[0]}): "
            "something left them there; look at git status in it. Nothing was merged."
        )
    result.tip_before = head_commit(story_worktree)
    if is_ancestor(root, result.tip_before, result.attempt_commit):
        result.kind = "fast-forward"
        result.tip_after = fast_forward(story_worktree, result.attempt_commit)
        result.outcome = MERGED
        return
    result.kind = "real"
    try:
        begin_merge(story_worktree, result.attempt_commit)
    except MergeConflict as exc:
        _fail(result, [str(exc)])
        return
    try:
        baseline = read_baseline(root, result.run_id)
        result.checks, blocking, result.notes = run_checks(
            check_lines(plan, task), story_worktree, baseline, settings.test_timeout
        )
    except BaseException:
        abort_merge(story_worktree)
        raise
    if blocking:
        abort_merge(story_worktree)
        _fail(result, failure_text(blocking))
        return
    subject = f"Merge {result.key}: {' '.join(task['title'].split())}"[:SUBJECT_CHARS]
    result.tip_after = finish_merge(story_worktree, subject)
    result.outcome = MERGED


def merge_attempt(
    settings: Settings, run_id: str, key: str, number: int | None = None,
    engine: Engine | None = None,
) -> MergeResult:  # fmt: skip
    """Merge the Done attempt `number` of `key` (default: its newest). BuildError: refused."""
    root = project_root(settings)
    plan = approved_plan(root, run_id)
    task = find_task(plan, key)
    engine = init_db(engine)
    story_worktree = layout.story_worktree(settings.worktrees_dir, run_id)
    if not story_worktree.is_dir():
        raise BuildError(f"Run {run_id} has no story worktree: run prepare first.")
    branch = layout.story_branch(run_id)
    number, commit = _pick(engine, run_id, key, number)
    if is_ancestor(root, commit, f"refs/heads/{branch}"):
        raise BuildError(f"Attempt {number} of {key} is already merged into {branch}.")
    result = MergeResult(run_id, key, number, branch, commit)
    try:
        with merge_lock(run_directory(root, run_id)):
            _merge_locked(settings, result, plan, task, story_worktree)
    except LockError as exc:
        raise BuildError(str(exc)) from None
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, run_id, key, number)
        now = datetime.now(UTC)
        if result.merged:
            tests = bool(result.checks) and all(row["ok"] for row in result.checks) or None
            merge_rows.record_merge(
                session, attempt, sub, kind=result.kind, commit=result.tip_after,
                tests_passed=tests, now=now,
            )  # fmt: skip
        else:
            merge_rows.fail_merge(session, attempt, sub, reason="; ".join(result.reasons), now=now)
    return result
