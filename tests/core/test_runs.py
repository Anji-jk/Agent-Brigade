import re
from datetime import UTC, datetime

import pytest

from core import runs

DAY = datetime(2026, 11, 12, 23, 59, tzinfo=UTC)


def test_a_run_id_is_the_story_key_the_date_and_4_hex_characters():
    run_id = runs.new_run_id("SMT-56", now=lambda: DAY)
    assert re.fullmatch(r"SMT-56-20261112-[0-9a-f]{4}", run_id)
    assert runs.validate_run_id(run_id) == run_id


def test_a_used_id_is_made_again():
    used = set()
    for _ in range(50):
        used.add(runs.new_run_id("SMT-56", taken=used.__contains__))
    assert len(used) == 50


def test_when_every_id_is_taken_it_says_so():
    with pytest.raises(runs.RunIdError, match="No free run id for SMT-56"):
        runs.new_run_id("SMT-56", taken=lambda _run_id: True)


@pytest.mark.parametrize("bad", ["", "smt-56", "SMT", "SMT-0", "../SMT-1", None])
def test_a_run_id_needs_a_real_story_key(bad):
    with pytest.raises(runs.RunIdError, match="Not a story key"):
        runs.new_run_id(bad)


def test_old_run_ids_stay_valid():
    assert runs.validate_run_id("run-20261112-090730-435234") == "run-20261112-090730-435234"


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "-run", "x" * 65, None, 7, "run 1"])
def test_anything_that_is_not_a_run_id_is_refused(bad):
    with pytest.raises(runs.RunIdError):
        runs.validate_run_id(bad)


def test_a_run_folder_is_inside_the_projects_brigade_folder(tmp_path):
    folder = runs.run_directory(tmp_path, "run-1")
    assert folder == tmp_path / ".agent-brigade" / "runs" / "run-1"
    assert not (tmp_path / ".agent-brigade").exists()  # only the path, nothing created


def test_the_project_folder_is_ignored_by_git_and_an_existing_ignore_is_kept(tmp_path):
    folder = runs.project_folder(tmp_path)
    assert (folder / ".gitignore").read_text() == "*\n"
    (folder / ".gitignore").write_text("* # mine\n")
    runs.project_folder(tmp_path)
    assert (folder / ".gitignore").read_text() == "* # mine\n"


def test_utc_now_has_a_utc_offset():
    assert runs.utc_now().endswith("+00:00")
