import pytest

from pipeline.documenting.doc_kind import (
    documentation_keys,
    is_documentation_task,
    is_documentation_title,
)


@pytest.mark.parametrize(
    "title",
    [
        "Documentation: user docs for the skill gap report",
        "documentation: lower case",
        "  DOCUMENTATION: shouting, with spaces in front",
    ],
)
def test_a_documentation_title_is_recognised(title):
    assert is_documentation_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "Backend: skill gap report endpoint",
        "Write the documentation",
        "Documentation for the report",  # no colon: not the Publisher's form
        "Frontend: Documentation: the page",  # the prefix must come first
        "",
        None,
        42,
    ],
)
def test_anything_else_is_not(title):
    assert not is_documentation_title(title)


def test_a_task_without_a_title_is_not_documentation():
    assert not is_documentation_task({"id": "T1", "jira_key": "SMT-1"})


def test_the_keys_come_back_in_plan_order():
    tasks = [
        {"jira_key": "SMT-57", "title": "Backend: endpoint"},
        {"jira_key": "SMT-58", "title": "Frontend: page"},
        {"jira_key": "SMT-60", "title": "Documentation: user docs"},
    ]
    assert documentation_keys(tasks) == ["SMT-60"]


def test_a_plan_without_a_documentation_task_gives_no_keys():
    assert documentation_keys([{"jira_key": "SMT-57", "title": "Backend: endpoint"}]) == []
