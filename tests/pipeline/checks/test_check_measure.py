from pipeline.checks import measure as m
from tests.pipeline.stages.stage_setup import FAIL, OK, line
from tests.pipeline.workspace.repo import make_repo


def task(**fields):
    return {"files": ["src"], "verification": [], **fields}


def test_the_changed_extra_and_protected_files_are_measured(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x", encoding="utf-8")
    (repo / "notes.txt").write_text("x", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("x", encoding="utf-8")
    report = m.measure_attempt(repo, task(verification=[OK]), "SMT-62", 1, timeout=60)
    assert report.changed == ["CLAUDE.md", "notes.txt", "src/a.py"]
    assert report.extra == ["CLAUDE.md", "notes.txt"]
    assert report.protected == ["CLAUDE.md"]
    assert report.verify == [] and not report.verify_ran and not report.passed
    assert "A protected path was changed: CLAUDE.md" in report.failures()


def test_the_verify_lines_run_in_the_worktree_and_each_result_is_kept(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x", encoding="utf-8")
    where = line("import os; print(os.path.basename(os.getcwd()))")
    report = m.measure_attempt(
        repo, task(verification=[where, FAIL, where]), "SMT-62", 1, timeout=60
    )
    assert [r.passed for r in report.verify] == [True, False]  # a repeated line runs once
    assert "r" in report.verify[0].output_tail
    assert report.verify_lines == 2 and report.passed  # a failing line is for the Reviewer
    assert report.failures() == [] and report.failed_verify() == [FAIL]


def test_a_task_that_changed_nothing_fails_even_when_its_lines_pass(tmp_path):
    repo = make_repo(tmp_path / "r")
    report = m.measure_attempt(repo, task(verification=[OK]), "SMT-62", 1, timeout=60)
    assert report.changed == [] and report.verify[0].passed
    assert report.failures() == ["The Builder changed no files."] and not report.passed


def test_files_outside_the_task_files_do_not_fail_it(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "other.py").write_text("x", encoding="utf-8")
    report = m.measure_attempt(repo, task(verification=[OK]), "SMT-62", 1, timeout=60)
    assert report.extra == ["other.py"] and report.passed


def test_a_task_without_verify_lines_passes_with_nothing_measured(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "src.py").write_text("x", encoding="utf-8")
    report = m.measure_attempt(repo, {"files": []}, "SMT-64", 1, timeout=60)
    assert report.verify == [] and report.verify_lines == 0 and report.passed
