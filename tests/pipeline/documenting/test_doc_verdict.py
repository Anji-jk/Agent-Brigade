import json

import pytest

from pipeline.checks.agent_reports import ReportError
from pipeline.documenting.doc_verdict import decide_review, parse_doc_review

LINES = {"README.md": 3}


def answer(**changes):
    data = {
        "verdict": "pass",
        "claims": [
            {"file": "README.md", "line": 2, "claim": "it saves", "status": "supported",
             "evidence": "ThemeToggle.jsx writes it"},
        ],
        "criteria": [{"criterion": 1, "met": True, "evidence": "lines 1-3"}],
        "problems": [],
    }  # fmt: skip
    data.update(changes)
    return "text before\n" + json.dumps(data)


def parsed(**changes):
    return parse_doc_review(answer(**changes), 1, LINES)


def test_a_complete_answer_is_read():
    verdict = parsed()
    assert verdict.verdict == "pass" and verdict.claims[0].line == 2
    assert verdict.met == {1: True} and decide_review(verdict).passed


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"verdict": "maybe"}, "verdict must be"),
        ({"claims": [{"file": "x.md", "line": 1, "claim": "c", "status": "supported",
                      "evidence": "e"}]}, "not one of the documents"),
        ({"claims": [{"file": "README.md", "line": 9, "claim": "c", "status": "supported",
                      "evidence": "e"}]}, "has 3 lines"),
        ({"claims": [{"file": "README.md", "line": 1, "claim": "c", "status": "fine",
                      "evidence": "e"}]}, "status must be one of"),
        ({"claims": [{"file": "README.md", "line": 1, "claim": "c", "status": "supported",
                      "evidence": ""}]}, "evidence must not be empty"),
        ({"claims": []}, "judges no claim"),
        ({"criteria": []}, "did not judge criteria: 1"),
        ({"criteria": [{"criterion": 1, "met": True}, {"criterion": 1, "met": True}]},
         "more than once"),
        ({"criteria": [{"criterion": 2, "met": True}]}, "from 1 to 1"),
        ({"criteria": [{"criterion": 1, "met": "yes"}]}, "met must be true or false"),
    ],
)  # fmt: skip
def test_an_answer_that_is_not_the_report_is_unusable(change, message):
    with pytest.raises(ReportError, match=message):
        parsed(**change)


def test_a_document_with_no_lines_needs_no_claims():
    verdict = parse_doc_review(answer(claims=[]), 1, {"README.md": 0})
    assert verdict.claims == []


def test_a_pass_beside_a_contradicted_claim_is_a_fail_naming_it():
    bad = {"file": "README.md", "line": 3, "claim": "3 tasks", "status": "contradicted",
           "evidence": "facts show 2"}  # fmt: skip
    decision = decide_review(parsed(claims=[bad]))
    assert not decision.passed
    assert decision.problems == ["README.md line 3 is contradicted: 3 tasks (facts show 2)"]
    assert decision.feedback().startswith("- README.md line 3")


def test_an_unmet_criterion_and_the_reviewers_own_problems_fail():
    verdict = parsed(
        criteria=[{"criterion": 1, "met": False, "evidence": "no usage section"}],
        problems=["the install steps are missing"],
    )
    problems = decide_review(verdict).problems
    assert "criterion 1 is not met: no usage section" in problems
    assert "the install steps are missing" in problems


def test_a_fail_without_a_named_problem_still_fails():
    decision = decide_review(parsed(verdict="fail"))
    assert not decision.passed and "without naming a problem" in decision.problems[0]
