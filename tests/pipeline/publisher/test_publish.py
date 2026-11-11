import json
from pathlib import Path

import pytest

from pipeline.publisher import publish as publish_module
from pipeline.publisher import transcript
from pipeline.publisher.guard import Plan, PlannedStory, PlannedSubtask
from pipeline.publisher.publish import created_note, publish, work_types
from pipeline.publisher.transcript import parse_transcript
from tests.doubles.jira import FakeJira

CRITERIA = "Acceptance criteria:\n- done"


def plan(epic="SMT-2", stories=1, subtasks=2):
    return Plan(
        tuple(
            PlannedStory(
                ref=f"S{n}",
                epic=epic,
                summary=f"Story {n}",
                description=CRITERIA,
                labels=("feature",),
                priority="High",
                subtasks=tuple(
                    PlannedSubtask(f"Story {n} task {m}", CRITERIA, ("backend",), "Medium")
                    for m in range(1, subtasks + 1)
                ),
            )
            for n in range(1, stories + 1)
        )
    )


@pytest.fixture
def jira():
    return (
        FakeJira().add("SMT-2", "epic", "Employee Profile").add("SMT-20", "story", "Old", "SMT-2")
    )


def created_requests(jira):
    return [
        body["fields"]
        for method, path, body in jira.requests
        if method == "POST" and path.endswith("/issue")
    ]


def test_stories_then_their_subtasks_are_created_and_read_back(jira):
    result = publish(plan(stories=2, subtasks=2), jira.client(), "SMT")

    assert result.ok and result.keys == [
        "SMT-100",
        "SMT-101",
        "SMT-102",
        "SMT-103",
        "SMT-104",
        "SMT-105",
    ]
    assert [(c.kind, c.parent) for c in result.created] == [
        ("story", "SMT-2"),
        ("sub-task", "SMT-100"),
        ("sub-task", "SMT-100"),
        ("story", "SMT-2"),
        ("sub-task", "SMT-103"),
        ("sub-task", "SMT-103"),
    ]
    first, second = created_requests(jira)[:2]
    assert first["issuetype"] == {"name": "Story"} and first["parent"] == {"key": "SMT-2"}
    assert first["labels"] == ["feature"] and first["priority"] == {"name": "High"}
    assert second["issuetype"] == {"name": "Subtask"} and second["parent"] == {"key": "SMT-100"}
    reads = [
        path for method, path, _ in jira.requests if method == "GET" and "/issue/SMT-1" in path
    ]
    assert len(reads) == 6  # every created item is read back


def test_the_space_names_for_sub_tasks_are_used(jira):
    jira.issue_types[2]["name"] = "Sub-task"
    assert work_types(jira.client(), "SMT") == ("Story", "Sub-task")


def test_a_space_without_sub_tasks_creates_nothing(jira):
    jira.issue_types.pop()
    result = publish(plan(), jira.client(), "SMT")
    assert (
        result.created == []
        and result.error is not None
        and "no Story or no Sub-task" in result.error
    )


def test_jira_is_checked_again_before_anything_is_created(jira):
    jira.add("SMT-50", "story", "Story 1", "SMT-2")  # someone created it after the proposal
    result = publish(plan(), jira.client(), "SMT")
    assert result.created == [] and created_requests(jira) == []
    assert result.error is not None
    assert result.error.startswith("Nothing was created.") and "SMT-50" in result.error


def test_a_failure_part_way_stops_and_says_what_exists(jira):
    jira.fail_create_at = 3  # story, sub-task 1, then sub-task 2 fails
    result = publish(plan(stories=2, subtasks=2), jira.client(), "SMT")

    assert not result.ok and result.keys == ["SMT-100", "SMT-101"]
    assert len(created_requests(jira)) == 3  # nothing after the failure
    assert result.error is not None
    assert "Stopped while creating sub-task 'Story 1 task 2' under SMT-100" in result.error
    assert "Created before the stop: SMT-100, SMT-101. Nothing was deleted." in result.error
    assert not any(method == "DELETE" for method, _, _ in jira.requests)


def test_jira_down_creates_nothing(jira):
    jira.down = True
    result = publish(plan(), jira.client(), "SMT")
    assert result.created == [] and result.error is not None
    assert result.error.startswith("Nothing was created.")


def test_an_item_read_back_differently_is_reported(jira, monkeypatch):
    real = jira._create

    def wrong_parent(fields):
        response = real(fields)
        key = response.json()["key"]
        if fields["issuetype"]["name"] == "Subtask":
            jira.issues[key]["fields"]["parent"] = {"key": "SMT-20"}
        return response

    monkeypatch.setattr(jira, "_create", wrong_parent)
    result = publish(plan(subtasks=1), jira.client(), "SMT")
    assert result.mismatches == ["SMT-101 has parent SMT-20, planned SMT-100."]
    assert not result.ok


def test_the_note_for_the_agent_lists_what_was_created_and_is_hidden_in_previous_chats(jira):
    result = publish(plan(subtasks=1), jira.client(), "SMT")
    note = created_note(result)
    assert note.splitlines() == [
        publish_module.NOTE_START,
        "- story SMT-100 under SMT-2: Story 1",
        "- sub-task SMT-101 under SMT-100: Story 1 task 1",
        publish_module.NOTE_END,
    ]
    line = json.dumps(
        {"type": "user", "message": {"role": "user", "content": f"{note}\n\nThanks, now the docs"}}
    )
    assert [b.text for b in parse_transcript([line])] == ["Thanks, now the docs"]


def test_the_note_after_a_failure_says_so(jira):
    jira.fail_create_at = 1
    note = created_note(publish(plan(), jira.client(), "SMT"))
    assert "- nothing was created" in note and "Stopped:" in note


SAMPLE = Path(__file__).parent / "fixtures" / "transcript_sample.jsonl"


@pytest.fixture
def command(jira, monkeypatch):
    """The command, reading the real sample chat and talking to the fake Jira."""
    bubbles = parse_transcript(SAMPLE.read_text(encoding="utf-8").splitlines())
    monkeypatch.setattr(transcript, "read_chat", lambda _session: bubbles)
    monkeypatch.setattr(
        publish_module, "get_settings", lambda: type("S", (), {"jira_project_key": "SMT"})()
    )
    monkeypatch.setattr(publish_module.JiraClient, "from_settings", lambda _s: jira.client())
    jira.add("SMT-7", "epic", "Platform")
    return jira


def test_the_command_is_a_dry_run_without_yes(command, capsys):
    assert publish_module.main(["--session", "36849025-aeb6-40c9-8d9d-c6ed4d200016"]) == 0
    out = capsys.readouterr().out
    assert "Story under SMT-2: Email employees 30 days before a certificate expires" in out
    assert out.count("  Sub-task:") == 3 and "Dry run: nothing created" in out
    assert command.creates == 0


def test_the_command_creates_the_last_plan_of_the_chat_under_a_test_epic(command, capsys):
    code = publish_module.main(["--session", "x", "--epic", "smt-7", "--yes"])
    out = capsys.readouterr().out
    assert code == 0 and command.creates == 4
    assert "Created story SMT-100 under SMT-7" in out and "read back from Jira as planned" in out
