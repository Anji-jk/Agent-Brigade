from pathlib import Path

import pytest

from pipeline.documenting import __main__ as cli
from pipeline.planning.plan_file import PlanFileError

TASKS = [
    {"jira_key": "SMT-57", "title": "Backend: endpoint"},
    {"jira_key": "SMT-60", "title": "Documentation: user docs"},
]


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setattr(cli, "_project_root", lambda: Path("."))

    def use(tasks):
        monkeypatch.setattr(cli, "load_plan", lambda root, run_id: {"tasks": tasks})

    return use


def test_kind_names_the_documentation_task(plan, capsys):
    plan(TASKS)
    assert cli.main(["kind", "SMT-56-20261112-b729"]) == 0
    out = capsys.readouterr().out
    assert "SMT-60  documentation" in out and "SMT-57  build" in out


def test_kind_exits_2_when_there_is_none(plan, capsys):
    plan(TASKS[:1])
    assert cli.main(["kind", "SMT-56-20261112-b729"]) == 2
    assert "story report is written instead" in capsys.readouterr().out


def test_an_unreadable_plan_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_project_root", lambda: Path("."))

    def missing(root, run_id):
        raise PlanFileError("No plan found for run x.")

    monkeypatch.setattr(cli, "load_plan", missing)
    assert cli.main(["kind", "x"]) == 1
    assert "Refused: No plan found" in capsys.readouterr().err
