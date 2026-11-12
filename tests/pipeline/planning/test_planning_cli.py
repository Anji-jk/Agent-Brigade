import pytest

from pipeline.planning import __main__ as cli
from pipeline.planning.plan_file import load_plan
from pipeline.planning.planner import plan_story
from tests.pipeline.planning.planning_setup import GOOD, jira_board, planned, planner, project
from tests.pipeline.planning.story_samples import story
from tests.pipeline.planning.test_readiness import settings as make_settings


class Client:
    closed = False

    def close(self):
        Client.closed = True


@pytest.fixture
def jira(monkeypatch):
    monkeypatch.setattr(cli.JiraClient, "from_settings", staticmethod(lambda _s: Client()))
    monkeypatch.setattr(cli, "read_story", lambda _client, key, _space: story())


def use(monkeypatch, settings):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)


def test_plan_prints_the_plan(tmp_path, monkeypatch, capsys, jira):
    repo, settings = project(tmp_path)
    use(monkeypatch, settings)
    assert cli.main(["plan", "SMT-56"], planner(tmp_path, GOOD)) == 0
    out = capsys.readouterr().out
    assert out.startswith("Planning SMT-56.")
    assert "Plan for story SMT-56" in out and "Plan file:" in out
    assert Client.closed


def test_plan_shows_the_checks_when_not_ready(tmp_path, monkeypatch, capsys, jira):
    repo, settings = project(tmp_path)
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    use(monkeypatch, settings)
    assert cli.main(["plan", "SMT-56", "--skip-tests"], planner(tmp_path)) == 2
    assert "Checks before planning SMT-56" in capsys.readouterr().out


def test_plan_reports_a_refused_plan(tmp_path, monkeypatch, capsys, jira):
    repo, settings = project(tmp_path)
    use(monkeypatch, settings)
    assert cli.main(["plan", "SMT-56"], planner(tmp_path, "no", "no")) == 1
    assert "Not planned: The Planner's answer was refused twice" in capsys.readouterr().err


def test_show_prints_a_saved_plan_and_names_a_missing_one(tmp_path, monkeypatch, capsys):
    result, _, repo = planned(tmp_path)
    use(monkeypatch, make_settings(tmp_path, project_path=repo))
    assert cli.main(["show", result.run_id]) == 0
    assert f"Run ID:      {result.run_id}" in capsys.readouterr().out
    assert cli.main(["show", "run-missing"]) == 1
    assert "No plan found for run run-missing" in capsys.readouterr().err
    assert cli.main(["show", "../x"]) == 1


def test_show_needs_a_project(tmp_path, monkeypatch, capsys):
    use(monkeypatch, make_settings(tmp_path))
    assert cli.main(["show", "run-1"]) == 1
    assert "BRIGADE_PROJECT_PATH is empty" in capsys.readouterr().err


def test_plan_takes_a_budget(tmp_path, monkeypatch, capsys, jira):
    repo, settings = project(tmp_path)
    use(monkeypatch, settings)
    assert cli.main(["plan", "SMT-56", "--budget", "12"], planner(tmp_path, GOOD)) == 0
    assert "Budget:      $12 for planning and building this story" in capsys.readouterr().out


def test_replan_takes_your_idea_and_prints_the_new_plan(tmp_path, monkeypatch, capsys, jira):
    repo, settings = project(tmp_path)
    first = plan_story(story(), settings, planner(tmp_path, GOOD))
    use(monkeypatch, settings)
    assert (
        cli.main(["replan", first.run_id, "--changes", "Docs first."], planner(tmp_path, GOOD)) == 0
    )
    out = capsys.readouterr().out
    assert out.startswith(f"Re-planning SMT-56 from {first.run_id}.")
    assert f"Re-plan of:  {first.run_id}\nChanges:     Docs first." in out
    assert load_plan(repo, first.run_id)["approval"]["status"] == "superseded"
    assert cli.main(["show", first.run_id]) == 0
    assert "Status:      replaced by SMT-56-" in capsys.readouterr().out


def test_replan_without_an_idea_is_not_accepted(tmp_path, monkeypatch, jira):
    with pytest.raises(SystemExit):
        cli.main(["replan", "run-1"], planner(tmp_path))


def test_replan_of_a_missing_run_says_so(tmp_path, monkeypatch, capsys, jira):
    repo, settings = project(tmp_path)
    use(monkeypatch, settings)
    assert cli.main(["replan", "run-missing", "--changes", "x"], planner(tmp_path)) == 1
    assert "Cannot re-plan run-missing: No plan found" in capsys.readouterr().err


def test_approve_writes_the_links_and_says_what_it_did(tmp_path, monkeypatch, capsys):
    result, _, repo = planned(tmp_path)
    use(monkeypatch, make_settings(tmp_path, project_path=repo))
    board = jira_board()
    monkeypatch.setattr(cli.JiraClient, "from_settings", staticmethod(lambda _s: board.client()))
    assert cli.main(["approve", result.run_id]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"Approved {result.run_id} (SMT-56) at ")
    assert "  written: SMT-59 is blocked by SMT-58 (with a comment)" in out
    assert cli.main(["approve", result.run_id]) == 1
    assert "Not approved: Run " in capsys.readouterr().err


def test_approve_with_nothing_to_write_says_so(tmp_path, monkeypatch, capsys):
    result, _, repo = planned(tmp_path)
    use(monkeypatch, make_settings(tmp_path, project_path=repo))
    board = jira_board().block("SMT-59", "SMT-58")
    monkeypatch.setattr(cli.JiraClient, "from_settings", staticmethod(lambda _s: board.client()))
    assert cli.main(["approve", result.run_id]) == 0
    assert "  already in Jira: SMT-59 is blocked by SMT-58" in capsys.readouterr().out
