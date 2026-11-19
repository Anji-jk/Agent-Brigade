import pytest

from pipeline.jira_sync.catch_up import catch_up
from pipeline.stages import __main__ as cli
from pipeline.stages import story_loop as s
from pipeline.stages.errors import BuildError
from tests.pipeline.jira_sync.test_story_sync import board, status
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.test_story_loop import StoryRunner, project


def test_a_board_that_missed_the_whole_run_is_caught_up_from_the_report(tmp_path):
    jira = board()
    jira.down = True
    _, config, engine = project(tmp_path)
    s.run_story(config, RUN, StoryRunner(), engine=engine, jira=jira.client())
    assert status(jira, "SMT-62") == "To Do"
    jira.down = False
    assert catch_up(config, RUN, engine, jira.client()) == []
    assert [status(jira, k) for k in ("SMT-62", "SMT-63", "SMT-56")] == [
        "Done",
        "Done",
        "In Review",
    ]


def test_a_run_without_a_report_is_refused(tmp_path):
    _, config, engine = project(tmp_path)
    with pytest.raises(BuildError, match="no story report"):
        catch_up(config, RUN, engine, board().client())


def test_without_jira_set_up_it_says_so(tmp_path):
    _, config, engine = project(tmp_path)
    s.run_story(config, RUN, StoryRunner(), engine=engine)
    with pytest.raises(BuildError, match="JIRA_SITE_URL"):
        catch_up(config, RUN, engine)


def test_the_command_exits_1_with_the_reason(tmp_path, monkeypatch, capsys):
    _, config, _ = project(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: config)
    assert cli.main(["jira-mirror", RUN]) == 1
    assert "no story report" in capsys.readouterr().err
