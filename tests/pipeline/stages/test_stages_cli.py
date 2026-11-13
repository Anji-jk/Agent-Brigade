from pipeline.stages import __main__ as cli
from tests.pipeline.stages.builder_setup import FakeRunner, build_project
from tests.pipeline.stages.stage_setup import FAIL, MAKE_FILE, OK, RUN, approved_project


def use(monkeypatch, config):
    monkeypatch.setattr(cli, "get_settings", lambda: config)


def test_prepare_attempt_and_clean_from_the_command_line(tmp_path, monkeypatch, capsys):
    _, config, _ = approved_project(tmp_path, setup=[MAKE_FILE], checks=[OK])
    use(monkeypatch, config)
    assert cli.main(["prepare", RUN]) == 0
    out = capsys.readouterr().out
    assert f"Branch:    agent/{RUN} at " in out and "Ready for agents." in out
    assert "Warning: the baseline left 1 changed or new file(s)" in out
    assert cli.main(["attempt", RUN, "SMT-62"]) == 0
    assert "Ready for the Builder." in capsys.readouterr().out
    assert cli.main(["clean", RUN, "--discard"]) == 0
    assert capsys.readouterr().out.count("removed") == 2


def test_a_failed_line_exits_with_2_and_says_which(tmp_path, monkeypatch, capsys):
    _, config, _ = approved_project(tmp_path, checks=[FAIL])
    use(monkeypatch, config)
    assert cli.main(["prepare", RUN]) == 2
    out = capsys.readouterr().out
    assert "FAILED" in out and "(exit 3," in out and "Not ready" in out


def test_a_refusal_exits_with_1_and_the_reason(tmp_path, monkeypatch, capsys):
    _, config, _ = approved_project(tmp_path, status="waiting")
    use(monkeypatch, config)
    assert cli.main(["prepare", RUN]) == 1
    assert "approve its plan before building" in capsys.readouterr().err
    assert cli.main(["prepare", "no-such-run"]) == 1
    assert "No plan found" in capsys.readouterr().err


def test_build_prints_the_attempt_and_writes_its_report(tmp_path, monkeypatch, capsys):
    repo, config, engine = build_project(tmp_path)
    use(monkeypatch, config)
    monkeypatch.setattr("pipeline.stages.builder_run.init_db", lambda _engine=None: engine)
    runner = FakeRunner(write={"made.txt": "x"})
    assert cli.main(["build", RUN, "SMT-62"], runner) == 0
    out = capsys.readouterr().out
    assert "Attempt 1 of SMT-62" in out and "made.txt" in out and "Built." in out
    assert (repo / ".agent-brigade" / "runs" / RUN / "build" / "SMT-62-1.json").is_file()
    assert cli.main(["build", RUN, "SMT-62"], runner) == 1  # the same attempt twice is refused
    assert "already exists" in capsys.readouterr().err


def test_a_builder_that_stops_with_an_error_exits_with_2(tmp_path, monkeypatch, capsys):
    _, config, engine = build_project(tmp_path)
    use(monkeypatch, config)
    monkeypatch.setattr("pipeline.stages.builder_run.init_db", lambda _engine=None: engine)
    assert cli.main(["build", RUN, "SMT-62"], FakeRunner(error="it ran out")) == 2
    assert "Stopped: it ran out" in capsys.readouterr().out


def test_rows_prints_the_run_rows(tmp_path, monkeypatch, capsys):
    _, config, engine = build_project(tmp_path)
    use(monkeypatch, config)
    monkeypatch.setattr("pipeline.stages.builder_run.init_db", lambda _engine=None: engine)
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    assert cli.main(["build", RUN, "SMT-62"], FakeRunner()) == 0
    capsys.readouterr()
    assert cli.main(["rows", RUN]) == 0
    assert "agent_runs  #1 builder status=done" in capsys.readouterr().out
