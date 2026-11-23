from typing import Any

from pipeline.documenting.doc_decision import RETRY, decide_doc_task
from pipeline.documenting.doc_review_run import DocReview
from pipeline.documenting.doc_verdict import ReviewDecision


def review(problems=(), error=None):
    return DocReview(ReviewDecision(not problems, list(problems)), error=error)


def decide(**changes):
    values: dict[str, Any] = dict(
        documenter_error=None, check_failures=[], verify_defects=[], review=review(),
        last_round=False,
    )  # fmt: skip
    values.update(changes)
    return decide_doc_task(**values)


def test_nothing_wrong_is_done():
    assert decide().status == "done"


def test_a_documenter_that_did_not_finish_goes_to_a_person_without_asking_the_reviewer():
    decision = decide(documenter_error="out of turns", review=None)
    assert decision.status == "needs_review" and "out of turns" in decision.reasons[0]


def test_a_blocking_check_fails_the_attempt_with_feedback_for_the_next_one():
    decision = decide(check_failures=["The Builder changed no files."], review=None)
    assert decision.status == "failed"
    assert decision.feedback == "- The Builder changed no files."


def test_problems_in_the_writing_get_one_more_try_with_all_of_them_listed():
    decision = decide(
        verify_defects=["the check line failed: npm run build"], review=review(["line 2 is wrong"])
    )
    assert decision.status == RETRY
    assert decision.feedback == "- the check line failed: npm run build\n- line 2 is wrong"


def test_problems_after_the_second_try_need_a_person():
    decision = decide(review=review(["line 2 is wrong"]), last_round=True)
    assert decision.status == "needs_review" and decision.reasons == ["line 2 is wrong"]


def test_a_reviewer_that_did_not_finish_needs_a_person_even_in_the_first_round():
    assert decide(review=review(error="no usable answer")).status == "needs_review"
    assert decide(review=None).status == "needs_review"
