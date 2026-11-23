"""What becomes of a documentation attempt: done, retry once, failed or needs a person.

Pure: it reads what code measured and what the two agents said, and decides. Money is not spent
again on a problem code cannot explain: an agent that did not finish goes to a person. Problems
with the writing itself get one more try (the Documenter is told every problem), and a second
failure goes to a person with nothing committed.
"""

from dataclasses import dataclass, field

from pipeline.checks.decide import DONE, FAILED, NEEDS_REVIEW
from pipeline.documenting.doc_review_run import DocReview

RETRY = "retry"


@dataclass
class DocDecision:
    status: str  # done | retry | failed | needs_review
    reasons: list[str] = field(default_factory=list)
    feedback: str = ""  # what the Documenter is told (retry) or the next attempt (failed)


def _lines(problems: list[str]) -> str:
    return "\n".join(f"- {problem}" for problem in problems)


def decide_doc_task(
    *,
    documenter_error: str | None,
    check_failures: list[str],
    verify_defects: list[str],
    review: DocReview | None,
    last_round: bool,
) -> DocDecision:
    """`check_failures`: nothing written or a protected path changed. `verify_defects`: check
    lines that fail now and did not fail before the Documenter. `review`: None when not asked."""
    if documenter_error:
        return DocDecision(NEEDS_REVIEW, [f"The Documenter did not finish: {documenter_error}"])
    if check_failures:
        return DocDecision(FAILED, check_failures, _lines(check_failures))
    if review is None or review.error is not None:
        why = review.error if review else "the Reviewer was not asked"
        return DocDecision(NEEDS_REVIEW, [f"The Documentation Reviewer did not finish: {why}"])
    problems = [*verify_defects, *review.decision.problems]
    if not problems:
        return DocDecision(DONE, [])
    if not last_round:
        return DocDecision(RETRY, problems, _lines(problems))
    return DocDecision(NEEDS_REVIEW, problems, _lines(problems))
