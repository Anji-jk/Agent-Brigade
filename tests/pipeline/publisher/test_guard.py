import json
from pathlib import Path

import pytest

from pipeline.publisher import guard
from pipeline.publisher.guard import check_plan, find_plan_block, parse_plan, without_plan_block
from tests.doubles.jira import FakeJira

CRITERIA = "Context.\nAcceptance criteria:\n- it works"


def subtask(summary="Build the API", **extra):
    return {"summary": summary, "description": CRITERIA, "labels": ["backend"], **extra}


def story(summary="Certificate expiry reminder", epic="SMT-2", subtasks=None, **extra):
    return {
        "ref": "S1",
        "epic": epic,
        "summary": summary,
        "description": CRITERIA,
        "subtasks": [subtask()] if subtasks is None else subtasks,
        **extra,
    }


def plan(*stories):
    return json.dumps({"stories": list(stories) or [story()]})


def jira():
    return (
        FakeJira()
        .add("SMT-2", "epic", "Employee Profile, Skills & Certifications")
        .add("SMT-20", "story", "Upload a certificate", "SMT-2")
        .add("SMT-25", "story", "Learning Center entry", "SMT-4")
    )


def test_the_last_plan_block_is_taken_and_removed_from_the_text():
    reply = 'Old:\n```plan\n{"a": 1}\n```\nNew tree\n```plan\n{"b": 2}\n```'
    assert find_plan_block(reply) == '{"b": 2}'
    assert without_plan_block(reply) == "Old:\n\nNew tree"
    assert find_plan_block("no block here") is None


def test_a_good_plan_passes():
    fake = jira()
    check = check_plan(plan(), fake.client(), "SMT")
    assert check.ok and check.problems == ()
    assert check.plan is not None
    assert check.plan.counts() == {"stories": 1, "subtasks": 1}
    first = check.plan.as_dict()["stories"][0]
    assert first["epic"] == "SMT-2" and first["subtasks"][0]["labels"] == ("backend",)
    search_body = fake.requests[1][2]
    assert search_body is not None
    assert search_body["jql"] == 'project = "SMT" AND parent = SMT-2 ORDER BY key ASC'


@pytest.mark.parametrize(
    "item, expected",
    [
        (story(description="no criteria"), "no 'Acceptance criteria:' line"),
        (story(subtasks=[subtask(description="none")]), "sub-task 1: the description has no"),
        (story(subtasks=[subtask(labels=["two words"])]), "label 'two words' is not one word"),
        (story(subtasks=[subtask(priority="Urgent")]), "priority 'Urgent' is not one of"),
        (story(summary="x" * 256), "longer than 255 characters"),
        (story(summary="two\nlines"), "must be one line"),
        (story(epic=""), "'epic' is missing"),
        (story(subtasks=[subtask(), subtask()]), "appears twice under this story"),
        (story(subtasks="later"), "'subtasks' must be a list"),
    ],
)
def test_rule_breaks_are_named(item, expected):
    check = parse_plan(plan(item))
    assert not check.ok
    assert any(expected in p for p in check.problems), check.problems


def test_the_same_story_twice_in_the_plan_is_refused():
    check = parse_plan(plan(story(), story(summary="certificate  EXPIRY reminder")))
    assert any("appears twice in the plan" in p for p in check.problems)


@pytest.mark.parametrize(
    "raw, expected",
    [("{not json", "not valid JSON"), ('{"stories": []}', "no stories"), ("[1]", "no stories")],
)
def test_a_broken_plan_block_is_refused(raw, expected):
    check = parse_plan(raw)
    assert check.plan is None and expected in check.problems[0]


def test_too_many_stories_are_refused():
    many = [story(summary=f"Story {n}") for n in range(guard.MAX_STORIES + 1)]
    assert "split it" in parse_plan(plan(*many)).problems[0]


@pytest.mark.parametrize(
    "epic, expected",
    [
        ("SMT-99", "Epic SMT-99 does not exist"),
        ("SMT-20", "SMT-20 is a story, not an Epic"),
        ("OTHER-1", "OTHER-1 is not an Epic key of space SMT"),
    ],
)
def test_the_epic_must_be_a_real_epic_of_the_space(epic, expected):
    check = check_plan(plan(story(epic=epic)), jira().client(), "SMT")
    assert not check.ok and len(check.problems) == 1 and check.problems[0].startswith(expected)


def test_other_space_keys_are_refused_without_asking_jira():
    fake = jira()
    check_plan(plan(story(epic="OTHER-1")), fake.client(), "SMT")
    assert fake.requests == []


def test_a_story_that_already_exists_under_the_epic_is_refused():
    check = check_plan(plan(story(summary="upload a  Certificate")), jira().client(), "SMT")
    assert check.problems == (
        "Story 'upload a  Certificate' already exists under SMT-2 as SMT-20.",
    )


def test_rule_breaks_are_reported_before_jira_is_asked():
    fake = jira()
    check = check_plan(plan(story(description="none")), fake.client(), "SMT")
    assert not check.ok and fake.requests == []


def test_jira_down_is_reported_and_marked_not_fixable_by_the_agent():
    fake = jira()
    fake.down = True
    check = check_plan(plan(), fake.client(), "SMT")
    assert not check.ok and not check.fixable
    assert check.problems[0].startswith("Jira could not be checked")


def test_allowed_commands_are_the_ones_the_agent_definition_teaches():
    text = (Path(__file__).resolve().parents[3] / ".claude/agents/publisher.md").read_text(
        encoding="utf-8"
    )
    assert len(guard.ALLOWED_COMMANDS) == 3
    for command in guard.ALLOWED_COMMANDS:
        assert command.removesuffix(" *") in text
