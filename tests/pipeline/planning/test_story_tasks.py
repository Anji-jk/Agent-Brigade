import pytest

from pipeline.planning import story_tasks as st
from pipeline.planning.plan_fields import PlanValidationError
from tests.pipeline.planning.story_samples import story, work_item


def test_criteria_lose_their_list_markers_and_keep_their_words():
    text = "- one\n* two\n3. three\n4) four\n- [x] five\n\n  plain  "
    assert st.criteria_list(text) == ["one", "two", "three", "four", "five", "plain"]
    assert st.criteria_list(None) == []


def test_jira_fields_are_copied_in_jira_order():
    tasks = st.jira_tasks(story())
    assert [(t["id"], t["jira_key"]) for t in tasks] == [
        ("T1", "SMT-57"),
        ("T2", "SMT-58"),
        ("T3", "SMT-59"),
    ]
    assert tasks[0]["title"] == "Write the skills CSV formatter"
    assert tasks[0]["acceptance_criteria"] == [
        "Skill, level and date columns.",
        "Commas in names are quoted.",
    ]
    assert "Acceptance Criteria" in tasks[0]["description"]


def test_long_jira_text_is_cut_with_a_marker():
    long = work_item("SMT-57", "x" * 300, description="y" * 5000)
    (task,) = st.jira_tasks(story(long))
    assert len(task["title"]) == 200 and task["title"].endswith("(cut short)")
    assert len(task["description"]) == 4000


def test_subtasks_need_criteria_and_at_least_one_open_item():
    with pytest.raises(PlanValidationError, match="No acceptance criteria in SMT-58"):
        st.jira_tasks(story(work_item("SMT-57", "a"), work_item("SMT-58", "b", criteria="")))
    with pytest.raises(PlanValidationError, match="no open sub-tasks"):
        st.jira_tasks(story(work_item("SMT-57", "a", done=True)))


def test_more_than_thirty_open_subtasks_are_refused():
    many = [work_item(f"SMT-{n}", f"Item {n}") for n in range(100, 131)]
    with pytest.raises(PlanValidationError, match="at most 30"):
        st.jira_tasks(story(*many))
