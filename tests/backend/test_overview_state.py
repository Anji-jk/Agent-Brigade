from backend.services.overview import planned_tasks, run_state
from core.db.repositories.overview_rows import RunUsage

RUN = "SMT-61-20261113-6b1a"


def test_a_run_with_every_planned_task_merged_is_finished(tmp_path):
    assert run_state(tmp_path, RUN, RunUsage(merged=3), planned=3) == "finished"


def test_a_run_that_stopped_short_is_failed_when_a_task_is_in_error_else_stopped(tmp_path):
    broken = RunUsage(merged=1, statuses={"done": 1, "error": 1})
    waiting = RunUsage(merged=1, statuses={"done": 1, "blocked": 1})
    assert run_state(tmp_path, RUN, broken, planned=3) == "failed"
    assert run_state(tmp_path, RUN, waiting, planned=3) == "stopped"


def test_a_plan_that_cannot_be_read_has_no_count(tmp_path):
    assert planned_tasks(tmp_path, RUN) is None
