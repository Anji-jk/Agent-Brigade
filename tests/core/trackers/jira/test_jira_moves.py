import pytest

from core.settings import Settings
from core.trackers.jira.moves import NoPath, move_to
from core.trackers.jira.names import MANAGED_LABELS, StatusNames
from tests.doubles.jira import FakeJira


def board() -> FakeJira:
    return FakeJira().add("SMT-10", "story").add("SMT-11", "sub-task", parent="SMT-10")


def test_a_direct_transition_moves_the_issue():
    jira = board()
    move_to(jira.client(), "SMT-11", "In Progress")
    assert jira.moves == [("SMT-11", "In Progress")]


def test_the_target_is_matched_without_regard_to_case():
    jira = board()
    move_to(jira.client(), "SMT-11", "in progress")
    assert jira.moves == [("SMT-11", "In Progress")]


def test_without_a_direct_transition_it_goes_through_the_middle_status():
    jira = board()
    jira.workflow = {"To Do": ["In Progress"], "In Progress": ["Done", "To Do"]}
    move_to(jira.client(), "SMT-11", "Done", via="In Progress")
    assert jira.moves == [("SMT-11", "In Progress"), ("SMT-11", "Done")]


def test_no_way_to_the_target_is_an_error_and_the_issue_is_put_back():
    jira = board()
    jira.workflow = {"To Do": ["In Progress"], "In Progress": ["To Do"]}
    with pytest.raises(NoPath, match="Done"):
        move_to(jira.client(), "SMT-11", "Done", via="In Progress", current="To Do")
    assert jira.issues["SMT-11"]["fields"]["status"]["name"] == "To Do"  # put back, not half way


def test_the_middle_status_is_not_tried_when_it_is_the_target():
    jira = board()
    jira.workflow = {"To Do": ["Done"]}
    with pytest.raises(NoPath):
        move_to(jira.client(), "SMT-11", "In Progress", via="In Progress")


def test_labels_are_added_and_removed_in_one_call():
    jira = FakeJira().add("SMT-10", "story", labels=["keep", "brigade-error"])
    jira.client().edit_labels("SMT-10", ["brigade-stopped"], ["brigade-error"])
    assert jira.issues["SMT-10"]["fields"]["labels"] == ["keep", "brigade-stopped"]


def test_the_status_names_of_a_space_are_read():
    assert board().client().status_names("SMT") == {
        "To Do",
        "In Progress",
        "In Review",
        "Done",
        "Error",
    }


def test_status_names_default_and_are_changed_in_settings():
    default = StatusNames.from_settings(Settings.model_construct())
    assert default.name("in_review") == "In Review"
    mine = StatusNames.from_settings(
        Settings.model_construct(jira_status_in_review="Needs review", jira_status_error="Broken")
    )
    assert (mine.name("in_review"), mine.name("error")) == ("Needs review", "Broken")
    assert mine.meaning_of("needs REVIEW") == "in_review"
    assert mine.meaning_of("Something else") is None


def test_the_labels_brigade_manages():
    assert MANAGED_LABELS == {
        "brigade-stopped",
        "brigade-blocked",
        "brigade-error",
        "brigade-unmerged",
        "brigade-merged",
    }
