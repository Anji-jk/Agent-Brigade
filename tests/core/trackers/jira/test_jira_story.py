import pytest

from core.trackers.jira.story import (
    StoryError,
    acceptance_criteria,
    check_story_key,
    format_story,
    read_story,
)
from tests.doubles.jira import SITE, FakeJira

CRITERIA = "Do the thing.\n\nAcceptance criteria:\n- One works\n- Two works\n\nNotes: keep it small"


def board() -> FakeJira:
    return (
        FakeJira()
        .add("SMT-2", "epic", "Employee Profile")
        .add("SMT-10", "story", "Export skills", "SMT-2", "Export the matrix.", priority="High")
        .add("SMT-11", "sub-task", "Formatter", "SMT-10", CRITERIA, labels=("backend",))
        .add("SMT-12", "sub-task", "Command", "SMT-10", CRITERIA)
        .add("SMT-13", "sub-task", "Docs", "SMT-10", "No criteria here.")
        .add("SMT-14", "sub-task", "Old work", "SMT-10", CRITERIA, status="Done", done=True)
        .block("SMT-12", "SMT-11")
    )


# ---------- keys ----------


@pytest.mark.parametrize("key", ["smt-9", " SMT-9 ", "AB_1-12"])
def test_good_keys_are_upper_cased(key):
    assert check_story_key(key) == key.strip().upper()


@pytest.mark.parametrize("key", ["", "SMT", "SMT-0", "9-SMT", "SMT 9", "SMT-9; drop"])
def test_bad_keys_are_refused(key):
    with pytest.raises(StoryError, match="not a Jira key"):
        check_story_key(key)


def test_a_key_from_another_space_is_refused():
    with pytest.raises(StoryError, match="not in the Jira space SMT"):
        check_story_key("KAN-9", "smt")


# ---------- acceptance criteria ----------


def test_criteria_stop_at_the_next_label():
    assert acceptance_criteria(CRITERIA) == "- One works\n- Two works"


def test_criteria_on_the_label_line_and_as_heading():
    assert acceptance_criteria("Acceptance criteria: it saves") == "it saves"
    text = "## Acceptance Criteria\n  1. first\n  2. second\n## Dependencies\nSMT-1"
    assert acceptance_criteria(text) == "1. first\n2. second"


def test_bold_label_counts():
    assert acceptance_criteria("**Acceptance criteria:**\n- yes") == "- yes"


def test_no_criteria_gives_none():
    assert acceptance_criteria("Just a description.") is None
    assert acceptance_criteria("Acceptance criteria:\n\nNotes: nothing above") is None


def test_an_unknown_label_does_not_end_the_criteria():
    text = "Acceptance criteria:\n- Amount: exact\n- Date: ISO"
    assert acceptance_criteria(text) == "- Amount: exact\n- Date: ISO"


# ---------- reading a story ----------


def test_reads_story_epic_and_subtasks_in_order():
    story = read_story(board().client(), "smt-10", "SMT")
    assert story.story.key == "SMT-10"
    assert story.story.priority == "High"
    assert story.story.url == f"{SITE}/browse/SMT-10"
    assert story.epic is not None and (story.epic.key, story.epic.summary) == (
        "SMT-2",
        "Employee Profile",
    )
    assert [s.key for s in story.subtasks] == ["SMT-11", "SMT-12", "SMT-13", "SMT-14"]
    assert [s.key for s in story.open_subtasks()] == ["SMT-11", "SMT-12", "SMT-13"]


def test_subtask_fields_criteria_and_blockers():
    story = read_story(board().client(), "SMT-10")
    formatter, command, docs, old = story.subtasks
    assert formatter.labels == ("backend",)
    assert formatter.acceptance_criteria == "- One works\n- Two works"
    assert docs.acceptance_criteria is None
    assert command.blocked_by == ("SMT-11",)
    assert formatter.blocked_by == ()
    assert old.done and old.status == "Done"


def test_blockers_outside_the_story_are_ignored():
    jira = board().add("SMT-30", "sub-task", "Elsewhere", "SMT-20").block("SMT-11", "SMT-30")
    story = read_story(jira.client(), "SMT-10")
    assert story.subtasks[0].blocked_by == ()


def test_a_story_without_subtasks():
    lonely = FakeJira().add("SMT-5", "story", "Alone")
    story = read_story(lonely.client(), "SMT-5")
    assert story.subtasks == () and story.epic is None


def test_missing_story_is_refused():
    with pytest.raises(StoryError, match="SMT-99 was not found"):
        read_story(board().client(), "SMT-99")


def test_epic_and_subtask_are_refused():
    with pytest.raises(StoryError, match="is an epic"):
        read_story(board().client(), "SMT-2")
    with pytest.raises(StoryError, match="sub-task; plan its story SMT-10"):
        read_story(board().client(), "SMT-11")


def test_reading_writes_nothing():
    jira = board()
    read_story(jira.client(), "SMT-10")
    assert {method for method, path, _ in jira.requests} <= {"GET", "POST"}
    assert all(
        path.endswith("/search/jql") for method, path, _ in jira.requests if method == "POST"
    )


# ---------- printing ----------


def test_format_lists_criteria_blockers_and_what_is_missing():
    text = format_story(read_story(board().client(), "SMT-10"))
    assert "Story:   SMT-10  Export skills" in text
    assert "Epic:    SMT-2  Employee Profile" in text
    assert "Sub-tasks: 4 (3 open)" in text
    assert "blocked by SMT-11" in text
    assert "        - One works" in text
    assert "acceptance criteria: NONE FOUND" in text
    assert text.endswith('Add an "Acceptance criteria:" part to their descriptions in Jira.')
    assert "No acceptance criteria found in: SMT-13." in text


def test_format_of_a_story_without_subtasks():
    lonely = FakeJira().add("SMT-5", "story", "Alone")
    text = format_story(read_story(lonely.client(), "SMT-5"))
    assert "Epic:    (none)" in text and text.endswith("The story has no sub-tasks.")


def test_source_links_end_the_criteria():
    text = "Acceptance criteria:\nThe icon renders.\nClicking it routes to /quiz.\nSource links: x"
    assert acceptance_criteria(text) == "The icon renders.\nClicking it routes to /quiz."
