import json

from pipeline.control import launch as lc
from pipeline.control import state as st

RUN = "SMT-61-20261113-6b1a"
OURS = f"python -m pipeline.stages loop {RUN}"


def report(folder, ok):
    (folder / "story-report.json").write_text(json.dumps({"ok": ok}), encoding="utf-8")


def alive(pid):
    return OURS if pid == 7 else None


def test_a_run_nobody_started_is_not_started(tmp_path):
    assert st.build_state(tmp_path, RUN, alive) == st.NOT_STARTED


def test_a_run_whose_loop_is_running_is_running(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    assert st.build_state(tmp_path, RUN, alive) == st.RUNNING


def test_a_run_with_every_task_merged_is_finished(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    report(tmp_path, True)
    assert st.build_state(tmp_path, RUN, lambda pid: None) == st.FINISHED


def test_a_run_whose_loop_ended_with_tasks_unmerged_is_stopped(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    report(tmp_path, False)
    assert st.build_state(tmp_path, RUN, lambda pid: None) == st.STOPPED


def test_a_launched_run_whose_process_is_gone_without_a_report_was_interrupted(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    assert st.build_state(tmp_path, RUN, lambda pid: None) == st.INTERRUPTED


def test_a_run_built_by_hand_is_known_by_its_report(tmp_path):
    report(tmp_path, True)
    assert st.build_state(tmp_path, RUN, lambda pid: None) == st.FINISHED


def test_a_running_loop_wins_over_the_report_of_an_earlier_loop(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    report(tmp_path, False)
    assert st.build_state(tmp_path, RUN, alive) == st.RUNNING


def test_a_damaged_report_counts_as_no_report(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    (tmp_path / "story-report.json").write_text("{", encoding="utf-8")
    assert st.build_state(tmp_path, RUN, lambda pid: None) == st.INTERRUPTED


def test_a_run_whose_loop_ended_with_a_task_stopped_on_request_is_paused(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    tasks = {"SMT-62": {"status": "stopped"}, "SMT-63": {"status": "waiting"}}
    (tmp_path / "story-report.json").write_text(
        json.dumps({"ok": False, "tasks": tasks}), encoding="utf-8"
    )
    assert st.build_state(tmp_path, RUN, lambda pid: None) == st.PAUSED


def test_a_cancelled_or_failed_task_alone_does_not_make_a_run_paused(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    tasks = {"SMT-62": {"status": "cancelled"}, "SMT-63": {"status": "blocked"}}
    (tmp_path / "story-report.json").write_text(
        json.dumps({"ok": False, "tasks": tasks}), encoding="utf-8"
    )
    assert st.build_state(tmp_path, RUN, lambda pid: None) == st.STOPPED
