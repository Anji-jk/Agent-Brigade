from pipeline.checks import decide as d

CRITERIA = ["Page follows the theme.", "Splash follows the theme."]


def green(**more) -> d.Findings:
    """Every stage ran and nothing is wrong."""
    base = {
        "reviewer_ok": True,
        "reviewer_verdict": "pass",
        "verify": [d.VerifyResult("npm run build", True, 0, baseline_failed=False)],
    }
    return d.Findings(CRITERIA, **{**base, **more})


def test_everything_in_order_is_done():
    decision = d.decide(green())
    assert decision.status == d.DONE
    assert decision.reasons == ["Every check passed."]


def test_a_verdict_without_the_reviewer_having_run_is_not_done():
    decision = d.decide(green(reviewer_ok=None, reviewer_verdict=None))
    assert decision.status == d.NEEDS_REVIEW


def test_a_tester_that_ran_must_have_given_a_usable_report():
    assert d.decide(green(tester_ran=True)).status == d.NEEDS_REVIEW
    assert d.decide(green(tester_ran=True, tester_ok=True)).status == d.DONE


def test_an_agent_that_crashed_or_timed_out_needs_a_person():
    decision = d.decide(green(infrastructure=["The Reviewer ran out of budget."]))
    assert decision.status == d.NEEDS_REVIEW
    assert decision.reasons == ["The Reviewer ran out of budget."]


def test_a_failing_check_cannot_be_outvoted_by_a_pass():
    build = d.VerifyResult("npm run build", False, 1, baseline_failed=False, output_tail="boom")
    decision = d.decide(green(verify=[build]))
    assert decision.status == d.FAILED
    assert decision.reasons == [
        "The check `npm run build` failed (exit 1). It passed before the Builder."
    ]


def test_a_check_that_did_not_exist_at_baseline_is_a_defect_too():
    new = d.VerifyResult("pytest -q tests/test_new.py", False, 1, baseline_failed=None)
    decision = d.decide(green(verify=[new]))
    assert decision.status == d.FAILED
    assert decision.reasons == ["The check `pytest -q tests/test_new.py` failed (exit 1)."]


def test_a_check_that_already_failed_at_baseline_is_left_to_the_reviewer():
    lint = d.VerifyResult("npx eslint .", False, 1, baseline_failed=True)
    decision = d.decide(green(verify=[lint]))
    assert decision.status == d.DONE
    assert "`npx eslint .` failed, and it also failed before the Builder." in decision.notes


def test_a_check_that_timed_out_is_a_defect_even_if_it_failed_at_baseline():
    slow = d.VerifyResult("npx eslint .", False, None, timed_out=True, baseline_failed=True)
    decision = d.decide(green(verify=[slow]))
    assert decision.status == d.FAILED
    assert "did not finish in time" in decision.reasons[0]


def test_each_blocking_finding_fails_the_attempt():
    cases = {
        "nothing_changed": (True, "The Builder changed no files."),
        "protected": (["CLAUDE.md"], "A protected path was changed: CLAUDE.md"),
        "tester_wrote_outside": (
            ["src/a.py"],
            "The Tester changed files that are not tests: src/a.py",
        ),
        "weakened_tests": (
            ["tests/a.py"],
            "Existing tests lost a test or an assertion: tests/a.py",
        ),
        "no_tests": (True, "The Tester named no tests."),
        "invalid_tests": (["x: no"], "The Tester named tests that cannot be used: x: no"),
        "suspected_defects": (["f(0) is None"], "The Tester suspects defects: f(0) is None"),
        "reviewer_verdict": ("fail", "The Reviewer's verdict is fail."),
        "reviewer_problems": (["No empty state."], "Reviewer: No empty state."),
    }
    for name, (value, reason) in cases.items():
        decision = d.decide(green(**{name: value}))
        assert decision.status == d.FAILED, name
        assert reason in decision.reasons, name


def test_a_criterion_with_no_test_and_no_reason_names_the_criterion():
    decision = d.decide(green(unnamed=[2]))
    assert decision.reasons == ["No test and no reason for: Splash follows the theme."]


def test_an_unmet_criterion_shows_its_text_and_the_reviewers_evidence():
    decision = d.decide(green(unmet={1: "headers still use bg-white"}))
    assert decision.status == d.FAILED
    assert decision.reasons == ["Not met: Page follows the theme. (headers still use bg-white)"]


def test_a_reason_for_having_no_test_is_a_note_and_not_a_failure():
    decision = d.decide(green(uncovered={1: "needs a browser"}, extra_files=["a.css"]))
    assert decision.status == d.DONE
    assert "No test for Page follows the theme.: needs a browser" in decision.notes
    assert "Files outside the task's list: a.css" in decision.notes


def test_the_feedback_carries_the_reasons_and_the_end_of_a_failing_output():
    build = d.VerifyResult(
        "npm run build", False, 1, baseline_failed=False, output_tail="x" * 3000 + "THE END"
    )
    findings = green(verify=[build], reviewer_problems=["No empty state."])
    decision = d.decide(findings)
    text = d.retry_feedback(1, findings, decision)
    assert text.startswith("Attempt 1 of this task was built, tested and reviewed, and failed.")
    assert "- Reviewer: No empty state." in text
    assert "The end of the output of `npm run build`:" in text
    assert text.count("x") < d.OUTPUT_CHARS
    assert "THE END" in text
    assert "new attempt on a clean checkout" in text


def test_the_feedback_leaves_out_a_check_that_the_baseline_explains():
    lint = d.VerifyResult("npx eslint .", False, 1, baseline_failed=True, output_tail="43 problems")
    findings = green(verify=[lint], reviewer_verdict="fail")
    text = d.retry_feedback(2, findings, d.decide(findings))
    assert "43 problems" not in text
    assert text.startswith("Attempt 2 of this task")
