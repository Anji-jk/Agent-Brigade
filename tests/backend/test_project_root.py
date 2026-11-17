"""The project's repository folder is asked of Git once, not on every page read."""

import pytest

from backend.services import run_lookup
from backend.services.planning_types import PlanningServiceError
from core.settings import Settings


def test_a_found_repository_is_not_asked_of_git_again(tmp_path, monkeypatch):
    asked = []

    def git(folder):
        asked.append(folder)
        return tmp_path

    monkeypatch.setattr(run_lookup, "repository_root", git)
    monkeypatch.setattr(run_lookup, "_ROOTS", {})
    settings = Settings.model_construct(project_path=tmp_path)
    assert run_lookup.project_root(settings) == tmp_path
    assert run_lookup.project_root(settings) == tmp_path
    assert asked == [tmp_path]


def test_a_failure_is_not_kept_so_fixing_the_folder_and_retrying_works(tmp_path, monkeypatch):
    from pipeline.workspace.git import GitError

    answers = [GitError("not a repository"), tmp_path]

    def git(folder):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(run_lookup, "repository_root", git)
    monkeypatch.setattr(run_lookup, "_ROOTS", {})
    settings = Settings.model_construct(project_path=tmp_path)
    with pytest.raises(PlanningServiceError):
        run_lookup.project_root(settings)
    assert run_lookup.project_root(settings) == tmp_path
