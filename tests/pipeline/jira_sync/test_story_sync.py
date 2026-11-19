"""The story loop with a fake Jira: the board follows the build, and never stops it."""

from pipeline.stages import story_loop as s
from tests.doubles.jira import FakeJira
from tests.pipeline.stages.stage_setup import FAIL, RUN
from tests.pipeline.stages.test_story_loop import StoryRunner, project


def board() -> FakeJira:
    return (
        FakeJira()
        .add("SMT-2", "epic")
        .add("SMT-56", "story", parent="SMT-2")
        .add("SMT-62", "sub-task", parent="SMT-56")
        .add("SMT-63", "sub-task", parent="SMT-56")
    )


def status(jira, key):
    return jira.issues[key]["fields"]["status"]["name"]


def said(jira, key):
    return [text for k, text in jira.comments if k == key]


def test_the_board_follows_a_story_that_merges(tmp_path):
    jira = board()
    _, config, engine = project(tmp_path)
    result = s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    assert result.ok
    assert [status(jira, k) for k in ("SMT-62", "SMT-63")] == ["Done", "Done"]
    assert status(jira, "SMT-56") == "In Review"
    assert jira.issues["SMT-56"]["fields"]["labels"] == ["brigade-unmerged"]
    assert status(jira, "SMT-2") == "In Progress"
    assert any(t.startswith("Attempt 1 started") for t in said(jira, "SMT-62"))
    assert any(
        "Merged into the story branch" in t and "$0.0000" not in t for t in said(jira, "SMT-62")
    )
    assert any("Story run" in t for t in said(jira, "SMT-56"))


def test_running_the_loop_again_writes_nothing_new(tmp_path):
    jira = board()
    _, config, engine = project(tmp_path)
    s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    comments, moves = list(jira.comments), list(jira.moves)
    s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    assert (jira.comments, jira.moves) == (comments, moves)


def test_a_task_failed_for_good_is_error_and_its_dependent_is_blocked(tmp_path):
    jira = board()
    _, config, engine = project(tmp_path, first_verify=(FAIL,), max_retries=0)
    s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    assert (status(jira, "SMT-62"), status(jira, "SMT-63")) == ("Error", "To Do")
    assert jira.issues["SMT-63"]["fields"]["labels"] == ["brigade-blocked"]
    assert status(jira, "SMT-56") == "In Review"
    assert jira.issues["SMT-56"]["fields"]["labels"] == ["brigade-error"]


def test_a_jira_that_is_down_never_stops_the_build(tmp_path):
    jira = board()
    jira.down = True
    _, config, engine = project(tmp_path)
    result = s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    assert result.ok


def test_with_sync_switched_off_jira_is_not_touched(tmp_path):
    jira = board()
    _, config, engine = project(tmp_path)
    config = config.model_copy(update={"jira_sync": False})
    s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    assert jira.requests == []


def test_without_jira_credentials_the_build_runs_as_before(tmp_path):
    _, config, engine = project(tmp_path)
    assert s.run_story(config, RUN, StoryRunner(), engine=engine).ok


def test_a_slow_jira_does_not_slow_the_build(tmp_path, monkeypatch):
    import time

    from pipeline.jira_sync import background

    monkeypatch.setattr(background, "CLOSE_WAIT", 0.2)
    jira = board()
    jira.delay = 1.0  # every Jira call takes a second: the updates alone need minutes
    _, config, engine = project(tmp_path)
    began = time.monotonic()
    result = s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    assert result.ok
    assert time.monotonic() - began < 120  # the build alone takes up to a minute on a slow disk
