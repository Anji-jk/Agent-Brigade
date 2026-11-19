from core.trackers.jira.names import (
    DONE,
    ERROR,
    IN_PROGRESS,
    IN_REVIEW,
    LABEL_BLOCKED,
    LABEL_ERROR,
    LABEL_STOPPED,
    LABEL_UNMERGED,
    TODO,
)
from pipeline.jira_sync.wanted import StoryFacts, TaskFacts, wanted_for
from pipeline.stages.story_report import (
    BLOCKED,
    CANCELLED,
    FAILED,
    MERGED,
    NEEDS_PERSON,
    PAUSED,
    WAITING,
)


def facts(*tasks, finished=False, epic: str | None = "SMT-2"):
    return StoryFacts("SMT-61", epic, "agent/RUN", list(tasks), finished, "REPORT TEXT")


def task(key="SMT-62", status=WAITING, attempts=0, running=False, detail="", cost=0.0):
    return TaskFacts(key, status, attempts, running, detail, cost)


def ids(wanted):
    return [comment_id for comment_id, _ in wanted.comments]


def test_nothing_started_everything_stays_to_do():
    got = wanted_for(facts(task("SMT-62"), task("SMT-63")))
    assert {k: w.status for k, w in got.items()} == {
        "SMT-62": TODO,
        "SMT-63": TODO,
        "SMT-61": TODO,
        "SMT-2": TODO,
    }
    assert all(not w.comments and not w.labels for w in got.values())


def test_a_running_attempt_moves_the_task_and_the_story_in_progress_with_comments():
    got = wanted_for(facts(task(attempts=2, running=True), task("SMT-63")))
    assert got["SMT-62"].status == IN_PROGRESS
    assert ids(got["SMT-62"]) == ["SMT-62:attempt:2"]
    assert "Attempt 2" in got["SMT-62"].comments[0][1]
    assert got["SMT-61"].status == IN_PROGRESS
    assert ids(got["SMT-61"]) == ["story:started"]
    assert "agent/RUN" in got["SMT-61"].comments[0][1]
    assert got["SMT-63"].status == TODO


def test_the_epic_is_moved_in_progress_only_from_to_do_once_a_story_started():
    got = wanted_for(facts(task(attempts=1, running=True)))
    assert got["SMT-2"].status == IN_PROGRESS
    assert got["SMT-2"].only_from_todo


def test_no_epic_means_no_epic_entry():
    assert "SMT-2" not in wanted_for(facts(task(attempts=1, running=True), epic=None))


def test_a_merged_task_is_done_with_its_cost():
    got = wanted_for(facts(task(status=MERGED, attempts=2, cost=0.1234)))
    assert got["SMT-62"].status == DONE
    assert ids(got["SMT-62"]) == ["SMT-62:merged"]
    assert "$0.1234" in got["SMT-62"].comments[0][1]


def test_a_task_merged_by_an_earlier_run_does_not_claim_zero_attempts():
    got = wanted_for(facts(task(status=MERGED, attempts=0, cost=0.2)))["SMT-62"]
    text = got.comments[0][1]
    assert "0 attempt" not in text and "earlier run" in text and "$0.2000" in text


def test_a_task_failed_for_good_is_error_with_the_reason():
    got = wanted_for(facts(task(status=FAILED, attempts=3, detail="used all its attempts")))
    assert got["SMT-62"].status == ERROR
    assert "used all its attempts" in got["SMT-62"].comments[0][1]


def test_a_task_a_person_stopped_stays_in_progress_with_the_label():
    for status in (PAUSED, CANCELLED, NEEDS_PERSON):
        got = wanted_for(facts(task(status=status, attempts=1, detail="why")))["SMT-62"]
        assert (got.status, got.labels) == (IN_PROGRESS, (LABEL_STOPPED,))
        assert "why" in got.comments[0][1]


def test_a_continued_task_loses_the_stopped_label():
    got = wanted_for(facts(task(status=PAUSED, attempts=1, running=True)))["SMT-62"]
    assert got.labels == ()


def test_a_blocked_task_stays_to_do_with_the_label_and_the_dependency():
    got = wanted_for(facts(task(status=BLOCKED, detail="SMT-62 did not finish")))["SMT-62"]
    assert (got.status, got.labels) == (TODO, (LABEL_BLOCKED,))
    assert "SMT-62 did not finish" in got.comments[0][1]


def test_between_two_attempts_the_task_stays_in_progress():
    got = wanted_for(facts(task(attempts=1, running=False)))["SMT-62"]
    assert got.status == IN_PROGRESS and got.comments == ()


def test_all_merged_and_finished_the_story_is_in_review_unmerged():
    got = wanted_for(facts(task(status=MERGED), finished=True))["SMT-61"]
    assert (got.status, got.labels) == (IN_REVIEW, (LABEL_UNMERGED,))
    assert got.comments[-1] == ("story:report:unmerged", "REPORT TEXT")


def test_a_failed_task_and_finished_the_story_is_in_review_with_the_error_label():
    got = wanted_for(facts(task(status=FAILED), task("SMT-63", status=BLOCKED), finished=True))
    assert (got["SMT-61"].status, got["SMT-61"].labels) == (IN_REVIEW, (LABEL_ERROR,))
    assert ids(got["SMT-61"])[-1] == "story:report:error"


def test_finished_only_because_a_person_must_act_the_story_stays_in_progress():
    got = wanted_for(facts(task(status=NEEDS_PERSON, attempts=1), finished=True))["SMT-61"]
    assert got.status == IN_PROGRESS and ids(got) == ["story:started"]
