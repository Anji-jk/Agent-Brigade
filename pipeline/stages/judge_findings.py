"""Turn the stages' reports into the Findings that decide() reads. No agent runs, nothing is spent.

check, test and the Reviewer each leave a record; this module reads them into one Findings: the
measured facts (what changed, how each Verify line ended, what the Tester wrote) and what the
agents claimed. A Verify line is compared with the same line at baseline, by its exact text.
"""

from typing import Any

from pipeline.checks.agent_reports import ReviewerReport
from pipeline.checks.decide import Findings, VerifyResult
from pipeline.stages.baseline import Baseline
from pipeline.stages.stage_inputs import Inputs


def verify_source(inputs: Inputs) -> list[dict[str, Any]]:
    """The Verify results to judge: those after the Tester if it ran, else those of check."""
    test = inputs.test
    if test and test.get("ran") and not test.get("error"):
        return list(test.get("verify", []))
    return list((inputs.check or {}).get("verify", []))


def verify_results(rows: list[dict[str, Any]], baseline: dict[str, Baseline]) -> list[VerifyResult]:
    results = []
    for row in rows:
        before = baseline.get(row["command"])
        results.append(
            VerifyResult(
                line=row["command"],
                passed=row.get("exit_code") == 0,
                exit_code=row.get("exit_code"),
                timed_out=bool(row.get("timed_out")),
                baseline_failed=None if before is None else before.failed,
                output_tail=str(row.get("output_tail") or ""),
            )
        )
    return results


def build_findings(inputs: Inputs, verify: list[VerifyResult]) -> Findings:
    """The measured facts and the Tester's part. The Reviewer's part is added by add_review."""
    check = inputs.check or {}
    findings = Findings(
        criteria=inputs.criteria,
        nothing_changed=not check.get("changed"),
        protected=list(check.get("protected", [])),
        extra_files=list(check.get("extra", [])),
        verify=verify,
    )
    test = inputs.test
    if not (test and test.get("ran")):
        return findings
    findings.tester_ran = True
    if test.get("error"):
        findings.infrastructure.append(f"The Tester did not finish: {test['error']}")
        return findings
    findings.tester_ok = True
    findings.tester_wrote_outside = list(test.get("outside", []))
    findings.weakened_tests = list(test.get("weakened", []))
    findings.no_tests = bool(test.get("no_tests"))
    findings.invalid_tests = list(test.get("invalid", []))
    findings.unnamed = [int(n) for n in test.get("unnamed", [])]
    findings.uncovered = {int(n): why for n, why in test.get("uncovered", {}).items()}
    findings.suspected_defects = list(test.get("suspected_defects", []))
    findings.tester_notes = list(test.get("notes", []))
    return findings


def add_review(findings: Findings, report: ReviewerReport) -> None:
    findings.reviewer_ok = True
    findings.reviewer_verdict = report.verdict
    findings.unmet = {n: report.evidence.get(n, "") for n, met in report.met.items() if not met}
    findings.reviewer_problems = list(report.problems)
    findings.reviewer_notes = list(report.notes)


def tester_lines(test: dict[str, Any] | None) -> list[str]:
    """What the Tester did, for the Reviewer's message. Empty when no Tester ran."""
    if not (test and test.get("ran")) or test.get("error"):
        return []
    lines = [f"Tester: {test.get('summary') or '(no summary)'}"]
    lines += [f"- criterion {n} tested by: {', '.join(t)}" for n, t in test["coverage"].items()]
    lines += [f"- criterion {n} not tested: {why}" for n, why in test["uncovered"].items()]
    lines += [f"- the Tester suspects: {text}" for text in test.get("suspected_defects", [])]
    if test.get("wrote"):
        lines.append("Files the Tester wrote: " + ", ".join(test["wrote"]))
    return lines
