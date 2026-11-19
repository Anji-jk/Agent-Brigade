import json

from core.trackers.jira.names import StatusNames
from pipeline.jira_sync.journal import Journal
from pipeline.jira_sync.mirror import mirror
from pipeline.jira_sync.wanted import Wanted
from tests.doubles.jira import FakeJira

NAMES = StatusNames("To Do", "In Progress", "In Review", "Done", "Error")


def board(**more) -> FakeJira:
    return (
        FakeJira()
        .add("SMT-2", "epic")
        .add("SMT-61", "story", parent="SMT-2")
        .add("SMT-62", "sub-task", parent="SMT-61", **more)
    )


def status(jira, key):
    return jira.issues[key]["fields"]["status"]["name"]


def labels(jira, key):
    return jira.issues[key]["fields"]["labels"]


def run(jira, wanted, tmp_path, names=NAMES):
    journal = Journal(tmp_path)
    problems = mirror(jira.client(), names, "SMT", wanted, journal)
    return problems, journal


def test_status_labels_and_comments_are_set(tmp_path):
    jira = board()
    wanted = {
        "SMT-62": Wanted("done", ("brigade-merged",), (("a", "Merged."),)),
        "SMT-61": Wanted("in_progress"),
    }
    problems, _ = run(jira, wanted, tmp_path)
    assert problems == []
    assert (status(jira, "SMT-62"), status(jira, "SMT-61")) == ("Done", "In Progress")
    assert labels(jira, "SMT-62") == ["brigade-merged"]
    assert jira.comments == [("SMT-62", "Merged.")]


def test_a_second_run_changes_nothing_and_repeats_no_comment(tmp_path):
    jira = board()
    wanted = {"SMT-62": Wanted("in_progress", ("brigade-stopped",), (("a", "Stopped."),))}
    run(jira, wanted, tmp_path)
    before = (list(jira.moves), list(jira.comments), jira.requests.copy())
    run(jira, wanted, tmp_path)
    assert (jira.moves, jira.comments) == before[:2]
    writes = [r for r in jira.requests[len(before[2]) :] if r[0] in ("POST", "PUT")]
    assert writes == []


def test_a_renamed_status_is_found_by_its_meaning(tmp_path):
    jira = board()
    jira.statuses = ["To Do", "In Progress", "Needs review", "Done", "Error"]
    names = StatusNames("To Do", "In Progress", "Needs review", "Done", "Error")
    run(jira, {"SMT-61": Wanted("in_review")}, tmp_path, names)
    assert status(jira, "SMT-61") == "Needs review"


def test_a_stale_brigade_label_goes_but_a_persons_label_stays(tmp_path):
    jira = board(labels=["mine", "brigade-error"])
    run(jira, {"SMT-62": Wanted("in_progress")}, tmp_path)
    assert labels(jira, "SMT-62") == ["mine"]


def test_to_do_goes_to_done_through_in_progress_when_the_workflow_needs_it(tmp_path):
    jira = board()
    jira.workflow = {"To Do": ["In Progress"], "In Progress": ["Done", "To Do"]}
    run(jira, {"SMT-62": Wanted("done")}, tmp_path)
    assert status(jira, "SMT-62") == "Done"


def test_the_epic_moves_only_from_to_do(tmp_path):
    jira = board()
    jira.issues["SMT-2"]["fields"]["status"]["name"] = "Done"
    run(jira, {"SMT-2": Wanted("in_progress", only_from_todo=True)}, tmp_path)
    assert status(jira, "SMT-2") == "Done"
    jira.issues["SMT-2"]["fields"]["status"]["name"] = "To Do"
    run(jira, {"SMT-2": Wanted("in_progress", only_from_todo=True)}, tmp_path)
    assert status(jira, "SMT-2") == "In Progress"


def test_jira_down_is_reported_not_raised(tmp_path):
    jira = board()
    jira.down = True
    problems, journal = run(jira, {"SMT-62": Wanted("done")}, tmp_path)
    assert problems and "unreachable" in problems[0]
    assert any(not line["ok"] for line in lines(tmp_path))
    assert journal is not None


def test_a_comment_that_failed_is_tried_again_next_time(tmp_path):
    jira = board()
    wanted = {"SMT-62": Wanted("todo", (), (("a", "Hello."),))}
    jira.fail_comments = True
    run(jira, wanted, tmp_path)
    jira.fail_comments = False
    run(jira, wanted, tmp_path)
    assert jira.comments == [("SMT-62", "Hello.")]


def test_a_status_jira_does_not_have_is_reported_once_and_the_rest_still_happens(tmp_path):
    jira = board()
    jira.statuses = ["To Do", "In Progress", "In Review", "Done"]  # no Error
    wanted = {"SMT-62": Wanted("error", ("brigade-stopped",), (("a", "It failed."),))}
    first, _ = run(jira, wanted, tmp_path)
    second, _ = run(jira, wanted, tmp_path)
    assert status(jira, "SMT-62") == "To Do"
    assert labels(jira, "SMT-62") == ["brigade-stopped"]
    assert jira.comments == [("SMT-62", "It failed.")]
    assert any("Error" in text and "In Review" in text for text in first)
    assert not any("Error" in text for text in second)


def test_no_way_to_a_status_is_a_problem_and_the_comment_is_still_written(tmp_path):
    jira = board()
    jira.workflow = {"To Do": ["In Progress"], "In Progress": ["To Do"]}
    wanted = {"SMT-62": Wanted("done", (), (("a", "Merged."),))}
    problems, _ = run(jira, wanted, tmp_path)
    assert any("no way to Done" in p for p in problems)
    assert status(jira, "SMT-62") == "To Do"
    assert jira.comments == [("SMT-62", "Merged.")]


def test_an_issue_jira_does_not_have_is_skipped(tmp_path):
    problems, _ = run(board(), {"SMT-99": Wanted("done")}, tmp_path)
    assert problems and "SMT-99" in problems[0]


def test_every_call_is_logged(tmp_path):
    jira = board()
    run(jira, {"SMT-62": Wanted("done", ("brigade-merged",), (("a", "x"),))}, tmp_path)
    actions = [line["action"] for line in lines(tmp_path)]
    assert {"status", "labels", "comment"} <= set(actions)


def lines(folder):
    path = folder / "jira-sync.jsonl"
    return [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines()]
