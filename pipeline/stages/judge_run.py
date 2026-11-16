"""Judge one attempt: the Reviewer reads it, code decides, and a Done attempt is committed.

judge_attempt   refuse an attempt that is already committed; else build the Findings from what
                check and the Tester measured, ask the Reviewer (unless the attempt has already
                failed a blocking check, or the Tester did not finish), decide(), commit if
                Done, and record the outcome

The Reviewer is paid even when a check failed, so that the retry is told every problem in one go.
It is not paid when nothing changed, a protected path changed or the Tester did not finish: the
outcome does not depend on what it would say. A claim never beats a measured fact (decide.py).
"""

from datetime import UTC, datetime

from sqlalchemy import Engine

from core.db import get_session, init_db
from core.db.repositories import judge_rows
from core.settings import Settings
from pipeline.checks.decide import DONE, NEEDS_REVIEW, Decision, Findings, decide, retry_feedback
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages.agent_ask import usage_of
from pipeline.stages.agent_requests import limits
from pipeline.stages.attempt_log import AttemptLog
from pipeline.stages.baseline import read_baseline
from pipeline.stages.builder_run import BuildError
from pipeline.stages.judge_commit import commit_attempt, diff_for_review
from pipeline.stages.judge_findings import (
    add_review,
    build_findings,
    tester_lines,
    verify_results,
    verify_source,
)
from pipeline.stages.judge_report import JudgeResult
from pipeline.stages.reviewer_prompt import reviewer_prompt
from pipeline.stages.reviewer_run import run_reviewer
from pipeline.stages.stage_inputs import Inputs, load_inputs
from pipeline.workspace.git import GitError

REASON_COLUMN_CHARS = 1000


def _skip_reason(findings: Findings) -> str | None:
    if findings.nothing_changed or findings.protected:
        return "the attempt has already failed a blocking check; the Reviewer cannot change that."
    if findings.infrastructure:
        return "the Tester did not finish, so a person decides and the Reviewer is not paid."
    return None


def _committed(engine: Engine, run_id: str, key: str, number: int) -> str | None:
    """The commit of this attempt when it was already judged Done, else None."""
    with get_session(engine) as session:
        _, attempt = judge_rows.rows_of_attempt(session, run_id, key, number)
        return attempt.commit_sha


def _review(
    engine: Engine, inputs: Inputs, findings: Findings, runner: AgentRunner, result: JudgeResult
) -> None:
    baseline = read_baseline(inputs.root, inputs.run_id)
    prompt = reviewer_prompt(
        inputs.task,
        changed=(inputs.check or {})["changed"],
        extra=findings.extra_files,
        verify=findings.verify,
        baseline_tails={line: b.output_tail for line, b in baseline.items()},
        tester_lines=tester_lines(inputs.test),
        diff=diff_for_review(inputs),
        builder_report=(inputs.build or {}).get("report", ""),
    )
    asked = run_reviewer(engine, inputs, runner, prompt)
    result.usage = usage_of(asked.reply)
    if asked.error is not None or asked.report is None:
        findings.infrastructure.append(f"The Reviewer did not finish: {asked.error}")
        return
    add_review(findings, asked.report)
    result.verdict = asked.report.verdict
    result.problems = list(asked.report.problems)
    result.criteria = [
        {"criterion": n, "text": text, "met": asked.report.met[n],
         "evidence": asked.report.evidence[n]}
        for n, text in enumerate(inputs.criteria, start=1)
    ]  # fmt: skip


def _commit(inputs: Inputs, decision: Decision, result: JudgeResult) -> Decision:
    """Commit a Done attempt. A commit that fails sends the attempt to a person instead."""
    try:
        result.commit, result.left_over = commit_attempt(inputs)
    except GitError as exc:
        return Decision(
            NEEDS_REVIEW, [f"Every check passed, but the commit failed: {exc}"], decision.notes
        )
    return decision


def judge_attempt(
    settings: Settings, run_id: str, key: str, runner: AgentRunner, number: int = 1,
    engine: Engine | None = None,
) -> JudgeResult:  # fmt: skip
    """Judge attempt `number` of `key`. BuildError: it was not built and checked yet."""
    inputs = load_inputs(settings, run_id, key, number)
    if inputs.check is None:
        raise BuildError(f"There is no check report for {key}: run check first.")
    engine = init_db(engine)
    sha = _committed(engine, run_id, key, number)
    if sha:  # judging again would pay the Reviewer for nothing and overwrite the Done record
        raise BuildError(
            f"Attempt {number} of {key} is already Done and committed ({sha[:12]}): "
            "nothing to judge. A new attempt is made by build."
        )
    baseline = read_baseline(inputs.root, run_id)
    verify = verify_results(verify_source(inputs), baseline)
    findings = build_findings(inputs, verify)
    result = JudgeResult(run_id, key, number, limits=limits(inputs.task, "reviewer"))
    log = AttemptLog(inputs.root, run_id, key, number)
    log.emit("judge_started")
    result.reviewer_skipped = _skip_reason(findings)
    if result.reviewer_skipped is None:
        _review(engine, inputs, findings, runner, result)
    decision = decide(findings)
    if decision.status == DONE:
        decision = _commit(inputs, decision, result)
    result.outcome, result.reasons, result.notes = decision.status, decision.reasons, decision.notes
    if decision.status == "failed":
        result.feedback = retry_feedback(number, findings, decision)
    result.verify = [
        {"line": v.line, "passed": v.passed,
         "how": "ok" if v.passed else "FAILED (new, a defect)" if v.defect
         else "FAILED (also at baseline, the Reviewer judges)"}
        for v in verify
    ]  # fmt: skip
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, run_id, key, number)
        judge_rows.record_outcome(
            session, attempt, sub, outcome=decision.status,
            reason="; ".join(decision.reasons)[:REASON_COLUMN_CHARS], commit_sha=result.commit,
            now=datetime.now(UTC),
        )  # fmt: skip
    log.emit(
        "judge_finished",
        outcome=result.outcome,
        reasons=result.reasons,
        commit=result.commit,
        reviewer_skipped=result.reviewer_skipped,
        verdict=result.verdict,
    )
    return result
