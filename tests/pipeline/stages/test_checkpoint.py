from pipeline.stages import checkpoint as cp
from tests.pipeline.stages.stage_setup import RUN


def test_a_new_attempt_has_finished_nothing_and_starts_with_the_builder(tmp_path):
    assert cp.completed(tmp_path, RUN, "SMT-62", 1) == []
    assert cp.resume_stage(tmp_path, RUN, "SMT-62", 1) == "builder"


def test_each_finished_stage_is_added_in_order_and_once(tmp_path):
    for stage in ("builder", "builder", "checks"):
        cp.save(tmp_path, RUN, "SMT-62", 1, stage)
    assert cp.completed(tmp_path, RUN, "SMT-62", 1) == ["builder", "checks"]
    assert cp.resume_stage(tmp_path, RUN, "SMT-62", 1) == "tester"


def test_the_order_is_kept_even_if_a_later_stage_is_saved_first(tmp_path):
    cp.save(tmp_path, RUN, "SMT-62", 1, "tester")
    cp.save(tmp_path, RUN, "SMT-62", 1, "builder")
    assert cp.completed(tmp_path, RUN, "SMT-62", 1) == ["builder", "tester"]


def test_once_the_tester_has_finished_the_judge_is_what_is_left(tmp_path):
    for stage in ("builder", "checks", "tester"):
        cp.save(tmp_path, RUN, "SMT-62", 1, stage)
    assert cp.resume_stage(tmp_path, RUN, "SMT-62", 1) == "judge"


def test_attempts_do_not_share_a_checkpoint(tmp_path):
    cp.save(tmp_path, RUN, "SMT-62", 1, "builder")
    assert cp.completed(tmp_path, RUN, "SMT-62", 2) == []
    assert cp.completed(tmp_path, RUN, "SMT-63", 1) == []


def test_a_damaged_file_reads_as_nothing_finished(tmp_path):
    cp.save(tmp_path, RUN, "SMT-62", 1, "builder")
    path = next(tmp_path.rglob(cp.FILE))
    path.write_text("{broken", encoding="utf-8")
    assert cp.completed(tmp_path, RUN, "SMT-62", 1) == []


def test_an_unknown_stage_is_refused(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        cp.save(tmp_path, RUN, "SMT-62", 1, "dancing")
