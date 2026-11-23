"""One documentation task end to end: Documenter, checks, Documentation Reviewer, decision, commit.

It takes the place of run_task for a task whose title starts with "Documentation:" and leaves
planning, publishing and every other task alone. The stages keep the names and the checkpoint
of an ordinary task so that Stop, Cancel and Continue work the same: the Documenter is the
"builder" stage, the checks are "checks", "tester" is a stage with no work (marked at once),
and the Reviewer and the decision are "judge".

Outcome: a pass is committed by code and merged by the story loop like any other attempt. A
Reviewer that finds problems sends the Documenter back once, in the same worktree, with every
problem listed; a second failure is Needs review and nothing is committed. A Documenter or
Reviewer that did not finish goes to a person at once.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories import attempt_rows, judge_rows
from core.settings import Settings
from pipeline.checks.decide import DONE
from pipeline.documenting.doc_attempt import OpenAttempt, open_attempt
from pipeline.documenting.doc_decision import RETRY, DocDecision, decide_doc_task
from pipeline.documenting.doc_requests import limits
from pipeline.documenting.doc_result import format_doc_result, write_doc_result
from pipeline.documenting.doc_review_run import DocReview, run_doc_reviewer
from pipeline.documenting.documenter_run import run_documenter
from pipeline.documenting.facts import collect_facts
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages import checkpoint
from pipeline.stages.attempt_log import AttemptLog
from pipeline.stages.baseline import read_baseline
from pipeline.stages.check_report import format_checks, write_check_report
from pipeline.stages.check_run import check_attempt
from pipeline.stages.interrupt import guard
from pipeline.stages.judge_commit import commit_attempt
from pipeline.stages.judge_findings import verify_results, verify_source
from pipeline.stages.judge_report import JudgeResult, format_judge, write_judge_report
from pipeline.stages.prepare import project_root
from pipeline.stages.retry import previous_feedback
from pipeline.stages.stage_inputs import load_inputs
from pipeline.workspace.git import GitError

REASON_COLUMN_CHARS = 1000


@dataclass
class DocTaskOutcome:
    text: str  # every stage's printout, in order
    judged: JudgeResult


def _write(
    settings: Settings, engine: Engine, runner: AgentRunner, opened: OpenAttempt, key: str,
    number: int, run_id: str, feedback: str, parts: list[str],
) -> str | None:  # fmt: skip
    """One Documenter pass. Returns an error text, or None when it finished well."""
    root = project_root(settings)
    if not opened.ready.ok:
        return "setup failed in the attempt worktree, so no Documenter was started."
    inputs = load_inputs(settings, run_id, key, number)
    doc = run_documenter(engine, inputs, runner, collect_facts(engine, root, run_id), feedback)
    parts.append(format_doc_result(doc, write_doc_result(root, doc)))
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, run_id, key, number)
        attempt_rows.finish_attempt(
            session, attempt, sub, outcome="built" if doc.ok else "error", reason=doc.error,
            stage="builder", status=attempt_rows.RUNNING if doc.ok else attempt_rows.ERROR,
            now=datetime.now(UTC),
        )  # fmt: skip
    if doc.ok:
        checkpoint.save(root, run_id, key, number, "builder")
    return doc.error or (f"outside the task's files: {doc.outside}" if doc.outside else None)


def review_attempt(
    settings: Settings, engine: Engine, runner: AgentRunner, run_id: str, key: str, number: int,

) -> tuple[list[str], list[str], DocReview | None, list[dict]]:  # fmt: skip
    """(check failures, verify defects, the review, the verify rows) of the attempt as it is."""
    root = project_root(settings)
    inputs = load_inputs(settings, run_id, key, number)
    failures = list((inputs.check or {}).get("failures", []))
    if failures:
        return failures, [], None, []
    baseline = read_baseline(root, run_id)
    verify = verify_results(verify_source(inputs), baseline)
    defects = [
        f"the check line failed and did not fail before: {v.line}" for v in verify if v.defect
    ]
    rows = [
        {"line": v.line, "passed": v.passed, "how": "ok" if v.passed else "FAILED"} for v in verify
    ]
    facts = collect_facts(engine, root, run_id)
    review = run_doc_reviewer(engine, inputs, runner, facts, list((inputs.check or {})["changed"]))
    return [], defects, review, rows


def _finish(
    settings: Settings, engine: Engine, run_id: str, key: str, number: int, decision: DocDecision,
    review: DocReview | None, verify: list[dict],
) -> JudgeResult:  # fmt: skip
    result = JudgeResult(run_id, key, number, limits=limits("reviewer"), verify=verify)
    result.outcome, result.reasons, result.feedback = (
        decision.status, decision.reasons, decision.feedback,
    )  # fmt: skip
    if review is None:
        result.reviewer_skipped = "a blocking check failed or the Documenter did not finish."
    else:
        result.usage = review.usage
        if review.verdict is not None:
            result.verdict, result.problems = review.verdict.verdict, review.verdict.problems
            result.criteria = [
                {"criterion": n, "text": text, "met": review.verdict.met[n],
                 "evidence": review.verdict.evidence[n]}
                for n, text in enumerate(
                    load_inputs(settings, run_id, key, number).criteria, start=1
                )
            ]  # fmt: skip
    if decision.status == DONE:
        try:
            inputs = load_inputs(settings, run_id, key, number)
            result.commit, result.left_over = commit_attempt(inputs)
        except GitError as exc:
            result.outcome = "needs_review"
            result.reasons = [f"Every check passed, but the commit failed: {exc}"]
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, run_id, key, number)
        judge_rows.record_outcome(
            session, attempt, sub, outcome=result.outcome,
            reason="; ".join(result.reasons)[:REASON_COLUMN_CHARS], commit_sha=result.commit,
            now=datetime.now(UTC),
        )  # fmt: skip
    return result


def run_doc_task(
    settings: Settings, run_id: str, key: str, runner: AgentRunner, number: int,
    engine: Engine, *, resume: bool = False,
) -> DocTaskOutcome:  # fmt: skip
    """Document, check, review and decide attempt `number` of `key`.

    TaskInterrupted: a person stopped or cancelled it. BuildError: it cannot start or continue."""
    root = project_root(settings)
    log = AttemptLog(root, run_id, key, number)
    done = checkpoint.completed(root, run_id, key, number) if resume else []
    first = checkpoint.resume_stage(root, run_id, key, number) if resume else "builder"

    def look(at: str, finished: bool = False) -> None:
        guard(engine, root, run_id, key, number, at, finished=finished)

    log.emit("attempt_continued" if resume else "attempt_started", attempt=number, stage=first)
    look("builder")
    opened = open_attempt(settings, run_id, key, number, engine, resume=resume, stage=first)
    parts: list[str] = []
    feedback = previous_feedback(root, run_id, key, number)
    decision, review, verify = DocDecision("needs_review", ["not run"]), None, []
    for round_no in (1, 2):
        first_round = round_no == 1
        error = None
        if not (first_round and "builder" in done):
            error = _write(settings, engine, runner, opened, key, number, run_id, feedback, parts)
            if error:
                decision = decide_doc_task(
                    documenter_error=error, check_failures=[], verify_defects=[], review=None,
                    last_round=True,
                )  # fmt: skip
                break
        if not (first_round and "checks" in done):
            look("checks")
            checked = check_attempt(settings, run_id, key, number, engine)
            parts.append(format_checks(checked, run_id, write_check_report(root, run_id, checked)))
            checkpoint.save(root, run_id, key, number, "checks")
        checkpoint.save(root, run_id, key, number, "tester")  # no Tester: nothing to do
        look("judge")
        log.emit("judge_started")
        failures, defects, review, verify = review_attempt(
            settings, engine, runner, run_id, key, number
        )
        decision = decide_doc_task(
            documenter_error=None, check_failures=failures, verify_defects=defects,
            review=review, last_round=not first_round,
        )  # fmt: skip
        if decision.status != RETRY:
            break
        feedback = decision.feedback
    result = _finish(settings, engine, run_id, key, number, decision, review, verify)
    parts.append(format_judge(result, write_judge_report(root, result)))
    log.emit(
        "judge_finished",
        outcome=result.outcome,
        reasons=result.reasons,
        commit=result.commit,
        reviewer_skipped=result.reviewer_skipped,
        verdict=result.verdict,
    )
    look("judge", finished=result.outcome == DONE)
    return DocTaskOutcome("\n\n".join(parts), result)
