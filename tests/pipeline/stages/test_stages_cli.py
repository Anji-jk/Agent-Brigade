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


def test_ready_merge_and_retry_from_the_command_line(tmp_path, monkeypatch, capsys):
    from tests.pipeline.stages.team_setup import TeamRunner, team_project

    repo, config, engine = team_project(tmp_path)
    use(monkeypatch, config)
    for module in ("builder_run", "tester_run", "judge_run", "check_run", "merge_run"):
        monkeypatch.setattr(f"pipeline.stages.{module}.init_db", lambda _engine=None: engine)
    monkeypatch.setattr(cli, "init_db", lambda _engine=None: engine)
    assert cli.main(["ready", RUN, "SMT-63"]) == 2  # SMT-62 is not merged yet
    assert "SMT-62 is not merged into the story branch yet" in capsys.readouterr().out
    assert cli.main(["ready", RUN, "SMT-62"]) == 0
    assert "SMT-62 may start" in capsys.readouterr().out
    assert cli.main(["task", RUN, "SMT-62"], TeamRunner()) == 0
    capsys.readouterr()
    assert cli.main(["retry", RUN, "SMT-62"], TeamRunner()) == 1  # it is Done: nothing to retry
    assert "is Done: merge it" in capsys.readouterr().err
    assert cli.main(["merge", RUN, "SMT-62"]) == 0
    out = capsys.readouterr().out
    assert "Fast-forward" in out and "MERGED: the story tip is now" in out
    assert (repo / ".agent-brigade" / "runs" / RUN / "merge" / "SMT-62-1.json").is_file()
    assert cli.main(["merge", RUN, "SMT-62"]) == 1
    assert "already merged" in capsys.readouterr().err
    assert cli.main(["ready", RUN, "SMT-63"]) == 0


def test_retry_tells_the_builder_what_the_failed_attempt_got_wrong(tmp_path, monkeypatch, capsys):
    from tests.pipeline.stages.team_setup import TeamRunner, team_project

    repo, config, engine = team_project(tmp_path, verify=(FAIL,))
    use(monkeypatch, config)
    for module in ("builder_run", "tester_run", "judge_run", "check_run"):
        monkeypatch.setattr(f"pipeline.stages.{module}.init_db", lambda _engine=None: engine)
    monkeypatch.setattr(cli, "init_db", lambda _engine=None: engine)
    runner = TeamRunner()
    assert cli.main(["task", RUN, "SMT-62"], runner) == 2
    capsys.readouterr()
    assert cli.main(["retry", RUN, "SMT-62"], runner) == 2  # still failing, but a second attempt
    out = capsys.readouterr().out
    assert "Attempt 2 of SMT-62: the Builder is told:" in out
    assert "| Attempt 1 of this task was built, tested and reviewed, and failed." in out
    assert [r.cwd.name for r in runner.of("builder")] == ["SMT-62-1", "SMT-62-2"]


def use_database(monkeypatch, engine):
    for module in (
        "builder_run",
        "tester_run",
        "judge_run",
        "check_run",
        "merge_run",
        "story_loop",
    ):
        monkeypatch.setattr(f"pipeline.stages.{module}.init_db", lambda _engine=None: engine)


def test_story_runs_every_task_and_exits_0_or_2(tmp_path, monkeypatch, capsys):
    from tests.pipeline.stages.test_story_loop import StoryRunner, project

    _, config, engine = project(tmp_path)
    use(monkeypatch, config)
    use_database(monkeypatch, engine)
    assert cli.main(["story", RUN], runner=StoryRunner()) == 0
    out = capsys.readouterr().out
    assert "2 of 2 tasks merged" in out and "The story is ready to review." in out


def test_story_exits_2_when_a_task_could_not_finish(tmp_path, monkeypatch, capsys):
    from tests.pipeline.stages.test_story_loop import StoryRunner, project

    _, config, engine = project(tmp_path, first_verify=(FAIL,), max_retries=0)
    use(monkeypatch, config)
    use_database(monkeypatch, engine)
    assert cli.main(["story", RUN], runner=StoryRunner()) == 2
    assert "The story is not finished." in capsys.readouterr().out


def test_reset_is_refused_while_the_run_has_branches_and_works_once_they_are_gone(
    tmp_path, monkeypatch, capsys
):
    from tests.pipeline.stages.test_reset import delete_branches
    from tests.pipeline.stages.test_story_loop import StoryRunner, project

    repo, config, engine = project(tmp_path)
    use(monkeypatch, config)
    use_database(monkeypatch, engine)
    monkeypatch.setattr("pipeline.stages.reset.init_db", lambda _engine=None: engine)
    assert cli.main(["story", RUN], runner=StoryRunner()) == 0
    assert cli.main(["clean", RUN, "--discard"]) == 0
    assert cli.main(["reset", RUN]) == 1
    assert f"git branch -D agent/{RUN}" in capsys.readouterr().err
    delete_branches(repo)
    assert cli.main(["reset", RUN]) == 0
    assert "is reset" in capsys.readouterr().out


def test_loop_runs_the_story_like_story_does(tmp_path, monkeypatch, capsys):
    from tests.pipeline.stages.test_story_loop import StoryRunner, project

    _, config, engine = project(tmp_path)
    use(monkeypatch, config)
    use_database(monkeypatch, engine)
    assert cli.main(["loop", RUN], runner=StoryRunner()) == 0
    assert "2 of 2 tasks merged" in capsys.readouterr().out


def test_loop_says_so_when_the_baseline_was_already_failing(tmp_path, monkeypatch, capsys):
    from pipeline.stages.loop_start import LoopRun
    from tests.pipeline.stages.stage_setup import approved_project

    _, config, _ = approved_project(tmp_path)
    use(monkeypatch, config)
    story = type("S", (), {"ok": True, "text": lambda self: "STORY TEXT"})()
    run = LoopRun(story=story, warnings=["Already failing before any agent worked: eslint."])
    monkeypatch.setattr("pipeline.stages.__main__.start_loop", lambda *a, **k: run)
    assert cli.main(["loop", RUN]) == 0
    out = capsys.readouterr().out
    assert "Already failing before any agent worked: eslint." in out and "STORY TEXT" in out
