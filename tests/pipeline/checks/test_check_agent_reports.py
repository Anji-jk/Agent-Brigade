import json

import pytest

from pipeline.checks import agent_reports as r


def reply(**data):
    return "Here is my report:\n```json\n" + json.dumps(data) + "\n```\nDone."


def test_the_last_json_object_is_taken_and_prose_around_it_is_ignored():
    text = 'first {"a": 1} then {"b": 2} and {broken'
    assert r.extract_json(text) == {"b": 2}


@pytest.mark.parametrize("text", [None, "", "   ", "no json here", "[1, 2]", 42])
def test_an_answer_without_a_json_object_is_unusable(text):
    with pytest.raises(r.ReportError):
        r.extract_json(text)


def test_a_tester_report_gives_the_coverage_and_the_reasons():
    report = r.parse_tester(
        reply(
            summary="ok",
            coverage=[
                {"criterion": 1, "tests": ["tests/test_a.py::test_one"]},
                {"criterion": 1, "tests": ["tests/test_a.py::test_two"]},
            ],
            uncovered=[{"criterion": 2, "reason": "needs a browser"}],
            suspected_defects=["f() returns None for 0"],
            notes=["slow"],
        ),
        2,
    )
    assert report.coverage == {1: ["tests/test_a.py::test_one", "tests/test_a.py::test_two"]}
    assert report.uncovered == {2: "needs a browser"}
    assert report.suspected_defects == ["f() returns None for 0"]
    assert report.notes == ["slow"]


@pytest.mark.parametrize(
    "data",
    [
        {"coverage": [{"criterion": 3, "tests": []}]},
        {"coverage": [{"criterion": True, "tests": []}]},
        {"coverage": ["tests/a.py"]},
        {"coverage": [{"criterion": 1, "tests": "tests/a.py"}]},
        {"uncovered": [{"criterion": 0, "reason": "x"}]},
        {"suspected_defects": "one"},
    ],
)
def test_a_tester_report_with_a_wrong_shape_is_unusable(data):
    with pytest.raises(r.ReportError):
        r.parse_tester(reply(**data), 2)


def good_review(**more):
    data = {
        "verdict": "pass",
        "criteria": [
            {"criterion": 1, "met": True, "evidence": "App.jsx line 4"},
            {"criterion": 2, "met": False, "evidence": "no empty state"},
        ],
        "problems": ["Empty state is missing."],
        "notes": ["Could be shorter."],
    }
    return reply(**{**data, **more})


def test_a_reviewer_report_gives_a_verdict_and_a_judgement_per_criterion():
    report = r.parse_reviewer(good_review(), 2)
    assert report.verdict == "pass"
    assert report.met == {1: True, 2: False}
    assert report.evidence[1] == "App.jsx line 4"
    assert report.problems == ["Empty state is missing."]
    assert report.notes == ["Could be shorter."]


@pytest.mark.parametrize(
    ("more", "message"),
    [
        ({"verdict": "approve"}, "verdict"),
        ({"criteria": [{"criterion": 1, "met": True}]}, "did not judge criteria: 2"),
        ({"criteria": []}, "did not judge criteria: 1, 2"),
        (
            {
                "criteria": [
                    {"criterion": 1, "met": True},
                    {"criterion": 1, "met": False},
                    {"criterion": 2, "met": True},
                ]
            },
            "more than once",
        ),
        ({"criteria": [{"criterion": 1, "met": "yes"}, {"criterion": 2, "met": True}]}, "met"),
        ({"problems": "one"}, "problems"),
    ],
)
def test_a_reviewer_report_that_skips_repeats_or_misreads_a_criterion_is_unusable(more, message):
    with pytest.raises(r.ReportError, match=message):
        r.parse_reviewer(good_review(**more), 2)


def test_long_text_is_cut():
    report = r.parse_reviewer(good_review(problems=["x" * 5000]), 2)
    assert len(report.problems[0]) == r.MAX_TEXT_FIELD
