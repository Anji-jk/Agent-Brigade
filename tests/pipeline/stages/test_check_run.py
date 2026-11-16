import json

import pytest

from core.db import get_session
from core.db.models import Check, SubTask
from core.files.atomic import write_json_atomic
from pipeline.planning.plan_file import load_plan, plan_path
from pipeline.stages import __main__ as cli
from pipeline.stages import builder_run as b
from pipeline.stages import check_run as c
from pipeline.stages.builder_rows import format_rows
from tests.pipeline.stages.builder_setup import FakeRunner, build_project
from tests.pipeline.stages.stage_setup import FAIL, OK, RUN


def project(tmp_path, *, files=("src",), verify=(OK,)):
    repo, config, engine = build_project(tmp_path)
    plan = load_plan(repo, RUN)
    plan["tasks"][0].update(files=list(files), verification=list(verify))
    write_json_atomic(plan_path(repo, RUN), plan)
    return repo, config, engine


def build(config, engine, write):
    return b.build_attempt(config, RUN, "SMT-62", FakeRunner(write=write), engine=engine)


def checks(engine):
    with get_session(engine) as session:
        return [
            (x.kind, x.passed, x.output_tail or "") for x in session.query(Check).order_by(Check.id)
        ]


def test_a_good_attempt_passes_and_its_checks_are_recorded(tmp_path):
    _, config, engine = project(tmp_path)
    build(config, engine, {"made.txt": "x"})
    report = c.check_attempt(config, RUN, "SMT-62", engine=engine)
    assert report.passed and report.extra == ["made.txt"]
    rows = checks(engine)
    assert [(kind, passed) for kind, passed, _ in rows] == [
        ("changes", True), ("protected", True), ("scope", False), ("verify", True),
    ]  # fmt: skip
    assert "outside the task's Files: made.txt" in rows[2][2] and rows[3][2].startswith("$ ")
    with get_session(engine) as session:
        assert session.query(SubTask).one().current_stage == "checks"


def test_a_failing_verify_line_is_recorded_for_the_reviewer_not_blocking(tmp_path):
    _, config, engine = project(tmp_path, verify=(OK, FAIL))
    build(config, engine, {"made.txt": "x"})
    report = c.check_attempt(config, RUN, "SMT-62", engine=engine)
    assert report.passed and report.failed_verify() == [FAIL]
    assert [passed for kind, passed, _ in checks(engine) if kind == "verify"] == [True, False]


def test_a_protected_change_fails_and_no_verify_line_runs(tmp_path):
    _, config, engine = project(tmp_path)
    build(config, engine, {"CLAUDE.md": "new rules", "ok.txt": "x"})
    report = c.check_attempt(config, RUN, "SMT-62", engine=engine)
    assert report.protected == ["CLAUDE.md"] and report.verify == []
    assert not any(kind == "verify" for kind, _, _ in checks(engine))


def test_checking_again_replaces_the_earlier_rows(tmp_path):
    _, config, engine = project(tmp_path)
    build(config, engine, {"made.txt": "x"})
    c.check_attempt(config, RUN, "SMT-62", engine=engine)
    c.check_attempt(config, RUN, "SMT-62", engine=engine)
    assert len(checks(engine)) == 4


def test_nothing_built_is_refused(tmp_path):
    _, config, engine = project(tmp_path)
    with pytest.raises(b.BuildError, match="build it first"):
        c.check_attempt(config, RUN, "SMT-62", engine=engine)
    with pytest.raises(b.BuildError, match="not a task"):
        c.check_attempt(config, RUN, "SMT-99", engine=engine)


def test_the_command_line_prints_writes_the_report_and_exits_by_the_result(
    tmp_path, monkeypatch, capsys
):
    repo, config, engine = project(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: config)
    monkeypatch.setattr("pipeline.stages.builder_run.init_db", lambda _engine=None: engine)
    monkeypatch.setattr("pipeline.stages.check_run.init_db", lambda _engine=None: engine)
    assert cli.main(["build", RUN, "SMT-62"], FakeRunner(write={"made.txt": "x"})) == 0
    capsys.readouterr()
    assert cli.main(["check", RUN, "SMT-62"]) == 0
    out = capsys.readouterr().out
    assert "Checks of attempt 1 of SMT-62" in out and "ok     " in out
    assert "Outside the task's Files (1), for the Reviewer: made.txt" in out
    assert "No blocking check failed." in out
    saved = json.loads(
        (repo / ".agent-brigade/runs" / RUN / "checks" / "SMT-62-1.json").read_text()
    )
    assert saved["passed"] is True and saved["extra"] == ["made.txt"]
    assert cli.main(["check", RUN, "SMT-63"]) == 1
    assert "build it first" in capsys.readouterr().err
    assert "checks      #" in format_rows(engine, RUN)
