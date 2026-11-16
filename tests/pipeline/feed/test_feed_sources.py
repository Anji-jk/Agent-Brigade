import json

import pytest

from core.runs import RunIdError
from pipeline.feed import sources
from pipeline.stages import attempt_log, events
from tests.pipeline.stages.stage_setup import RUN


def make_attempt(root, key="SMT-62", number=1, roles=("builder",)):
    log = attempt_log.AttemptLog(root, RUN, key, number)
    log.emit("attempt_started", attempt=number)
    for role in roles:
        path = attempt_log.agent_events_path(root, RUN, key, number, role)
        path.write_text(json.dumps({"type": "system", "subtype": "init"}) + "\n", encoding="utf-8")


def test_each_source_of_an_attempt_is_read_from_its_own_file(tmp_path):
    make_attempt(tmp_path, roles=("builder", "reviewer"))
    steps = sources.attempt_items(tmp_path, RUN, "SMT-62", 1, "orchestrator")
    agent = sources.attempt_items(tmp_path, RUN, "SMT-62", 1, "builder")
    assert steps[0].title == "attempt 1 started" and agent[0].kind == "start"


def test_the_sources_that_exist_are_listed_so_a_skipped_tester_has_no_tab(tmp_path):
    make_attempt(tmp_path, roles=("builder", "reviewer"))
    assert sources.available(tmp_path, RUN, "SMT-62", 1) == ["orchestrator", "builder", "reviewer"]
    assert sources.available(tmp_path, RUN, "SMT-99", 1) == []


def test_an_attempt_that_has_not_started_has_no_items(tmp_path):
    assert sources.attempt_items(tmp_path, RUN, "SMT-62", 3, "builder") == []


def test_the_story_log_is_read(tmp_path):
    events.record(tmp_path, RUN, "story_started", tasks=1, parallel=1)
    (item,) = sources.story_log_items(tmp_path, RUN)
    assert item.kind == "start"


@pytest.mark.parametrize("source", ["../x", "judge", "", "builder.events"])
def test_an_unknown_source_is_refused(tmp_path, source):
    with pytest.raises(sources.FeedError):
        sources.attempt_items(tmp_path, RUN, "SMT-62", 1, source)


@pytest.mark.parametrize("key", ["../../etc", "smt-62", "SMT-62/x", "", "SMT-"])
def test_a_task_key_that_is_not_a_key_is_refused(tmp_path, key):
    with pytest.raises(sources.FeedError):
        sources.attempt_items(tmp_path, RUN, key, 1, "builder")


@pytest.mark.parametrize("number", [0, -1, True, "1"])
def test_an_attempt_number_that_is_not_a_number_is_refused(tmp_path, number):
    with pytest.raises(sources.FeedError):
        sources.attempt_items(tmp_path, RUN, "SMT-62", number, "builder")


def test_a_run_id_that_is_not_a_run_id_is_refused(tmp_path):
    with pytest.raises(RunIdError):
        sources.story_log_items(tmp_path, "../x")
