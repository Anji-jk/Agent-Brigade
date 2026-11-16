"""Turn what was measured and what the agents claimed into the attempt's outcome. Pure: no I/O.

Ported from Agent Lab (execution/agents.py: Findings, problems, decide). A claim never beats a
measured fact: a Reviewer that says "pass" cannot outvote a failing test.

Outcomes (technical document 8.4):
  done          every stage produced evidence and nothing is wrong
  failed        a check found a defect; the Builder is told what and tries again (4.5)
  needs_review  the work could not be judged (an agent crashed, timed out, gave no usable report)

Verify lines are judged in two ways. A line that already failed at baseline (eslint on a project
whose lint is red) says nothing new: the Reviewer sees it and judges. A line that passed at
baseline, or did not exist then, and now fails is a defect found by code, and no verdict can
override it.
"""

from dataclasses import dataclass, field

DONE = "done"
FAILED = "failed"
NEEDS_REVIEW = "needs_review"
OUTPUT_CHARS = 1500
MAX_REASONS = 12
REASON_CHARS = 600


@dataclass(frozen=True)
class VerifyResult:
    line: str
    passed: bool
    exit_code: int | None = None
    timed_out: bool = False
    baseline_failed: bool | None = None  # True it failed at baseline, False it passed, None unknown
    output_tail: str = ""

    @property
    def defect(self) -> bool:
        """Failed in a way the baseline does not explain, or never finished."""
        return not self.passed and (self.timed_out or not self.baseline_failed)

    @property
    def judged_by_reviewer(self) -> bool:
        return not self.passed and not self.defect


@dataclass
class Findings:
    criteria: list[str]
    nothing_changed: bool = False
    protected: list[str] = field(default_factory=list)
    extra_files: list[str] = field(default_factory=list)  # a note, never a failure
    verify: list[VerifyResult] = field(default_factory=list)
    tester_ran: bool = False
    tester_ok: bool | None = None
    tester_wrote_outside: list[str] = field(default_factory=list)
    weakened_tests: list[str] = field(default_factory=list)
    no_tests: bool = False  # the Tester ran and named no test
    invalid_tests: list[str] = field(default_factory=list)
    unnamed: list[int] = field(default_factory=list)  # a criterion with no test and no reason
    uncovered: dict[int, str] = field(default_factory=dict)  # a stated reason: a note
    suspected_defects: list[str] = field(default_factory=list)
    tester_notes: list[str] = field(default_factory=list)
    reviewer_ok: bool | None = None
    reviewer_verdict: str | None = None
    unmet: dict[int, str] = field(default_factory=dict)  # criterion -> the Reviewer's evidence
    reviewer_problems: list[str] = field(default_factory=list)
    reviewer_notes: list[str] = field(default_factory=list)
    infrastructure: list[str] = field(default_factory=list)  # what stopped the judging


@dataclass(frozen=True)
class Decision:
    status: str
    reasons: list[str]
    notes: list[str]


def _criterion(findings: Findings, number: int) -> str:
    texts = findings.criteria
    return texts[number - 1] if 0 < number <= len(texts) else f"criterion {number}"


def _build_problems(f: Findings) -> list[str]:
    reasons: list[str] = []
    if f.nothing_changed:
        reasons.append("The Builder changed no files.")
    if f.protected:
        reasons.append("A protected path was changed: " + ", ".join(f.protected))
    for result in f.verify:
        if result.defect:
            what = (
                "did not finish in time"
                if result.timed_out
                else f"failed (exit {result.exit_code})"
            )
            seen = "" if result.baseline_failed is None else " It passed before the Builder."
            reasons.append(f"The check `{result.line}` {what}.{seen}".rstrip())
    return reasons


def _tester_problems(f: Findings) -> list[str]:
    reasons: list[str] = []
    if f.tester_wrote_outside:
        reasons.append(
            "The Tester changed files that are not tests: " + ", ".join(f.tester_wrote_outside)
        )
    if f.weakened_tests:
        reasons.append("Existing tests lost a test or an assertion: " + ", ".join(f.weakened_tests))
    if f.no_tests:
        reasons.append("The Tester named no tests.")
    if f.invalid_tests:
        reasons.append("The Tester named tests that cannot be used: " + "; ".join(f.invalid_tests))
    for number in f.unnamed:
        reasons.append(f"No test and no reason for: {_criterion(f, number)}")
    if f.suspected_defects:
        reasons.append("The Tester suspects defects: " + "; ".join(f.suspected_defects))
    return reasons


def _reviewer_problems(f: Findings) -> list[str]:
    reasons: list[str] = []
    if f.reviewer_verdict == "fail":
        reasons.append("The Reviewer's verdict is fail.")
    for number, evidence in f.unmet.items():
        reasons.append(f"Not met: {_criterion(f, number)}" + (f" ({evidence})" if evidence else ""))
    reasons += [f"Reviewer: {problem}" for problem in f.reviewer_problems]
    return reasons


def problems(f: Findings) -> list[str]:
    """Why the attempt has failed so far. Empty means nothing is wrong yet."""
    return _build_problems(f) + _tester_problems(f) + _reviewer_problems(f)


def notes(f: Findings) -> list[str]:
    """What is recorded for the Reviewer and the person, and never fails an attempt."""
    found = []
    if f.extra_files:
        found.append("Files outside the task's list: " + ", ".join(f.extra_files))
    for result in f.verify:
        if result.judged_by_reviewer:
            found.append(f"`{result.line}` failed, and it also failed before the Builder.")
    found += [f"No test for {_criterion(f, n)}: {why}" for n, why in f.uncovered.items()]
    found += [f"Tester: {note}" for note in f.tester_notes]
    found += [f"Reviewer: {note}" for note in f.reviewer_notes]
    return found


def decide(f: Findings) -> Decision:
    """The outcome and its reasons. Done needs evidence from every stage, not silence."""
    if f.infrastructure:
        return Decision(NEEDS_REVIEW, list(f.infrastructure), notes(f))
    reasons = problems(f)
    if reasons:
        return Decision(FAILED, reasons, notes(f))
    complete = (
        f.reviewer_ok is True
        and f.reviewer_verdict == "pass"
        and (f.tester_ok is True or not f.tester_ran)
    )
    if not complete:
        return Decision(
            NEEDS_REVIEW, ["The run ended before every check produced a result."], notes(f)
        )
    return Decision(DONE, ["Every check passed."], notes(f))


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split()) if limit == REASON_CHARS else text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def retry_feedback(attempt: int, f: Findings, decision: Decision) -> str:
    """What the next Builder is told: the reasons, and the end of each failing check's output."""
    lines = [f"Attempt {attempt} of this task was built, tested and reviewed, and failed."]
    lines.append("What was found:")
    lines += [f"- {_clip(reason, REASON_CHARS)}" for reason in decision.reasons[:MAX_REASONS]]
    if len(decision.reasons) > MAX_REASONS:
        lines.append(f"- ... and {len(decision.reasons) - MAX_REASONS} more")
    for result in f.verify:
        if result.defect:
            tail = result.output_tail.strip()
            lines += ["", f"The end of the output of `{result.line}`:"]
            lines.append(
                ("…" + tail[-(OUTPUT_CHARS - 1) :].lstrip())
                if len(tail) > OUTPUT_CHARS
                else tail or "(no output)"
            )
    lines += [
        "",
        "This is a new attempt on a clean checkout: the earlier attempt's changes are not here. "
        "Make the change again, and make sure these problems do not occur.",
    ]
    return "\n".join(lines)
