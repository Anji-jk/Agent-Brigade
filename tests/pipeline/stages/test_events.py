from pipeline.stages import events as e
from tests.pipeline.stages.stage_setup import RUN


def test_events_are_read_back_in_the_order_they_were_recorded(tmp_path):
    e.record(tmp_path, RUN, "story_started", tasks=2)
    e.record(tmp_path, RUN, "task_merged", key="SMT-62", attempt=1)
    found = e.read_events(tmp_path, RUN)
    assert [x["kind"] for x in found] == ["story_started", "task_merged"]
    assert found[1]["key"] == "SMT-62" and found[1]["attempt"] == 1 and found[0]["at"]


def test_a_run_without_events_reads_as_empty(tmp_path):
    assert e.read_events(tmp_path, RUN) == []


def test_a_torn_last_line_from_a_crash_is_skipped(tmp_path):
    e.record(tmp_path, RUN, "story_started")
    with e.events_path(tmp_path, RUN).open("a", encoding="utf-8") as handle:
        handle.write('{"kind": "task_sta')
    assert [x["kind"] for x in e.read_events(tmp_path, RUN)] == ["story_started"]
