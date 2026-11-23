from datetime import datetime

import pytest

from core.db import get_session, init_db, make_engine
from core.db.repositories import attempt_rows as rows
from core.db.repositories import merge_rows, story_runs
from pipeline.documenting.facts import FactsError, collect_facts
from pipeline.documenting.facts_format import format_facts
from pipeline.documenting.facts_model import facts_path, write_facts
from pipeline.planning.plan_file import PlanFileError
from tests.pipeline.stages.builder_setup import build_project
from tests.pipeline.stages.stage_setup import RUN, approved_project
from tests.pipeline.workspace.repo import git

NOW = datetime(2026, 11, 13, 10, 0)


class Reply:
    model_used, turns, cost_usd, duration_ms = "sonnet", 4, 0.25, 5000
    input_tokens = output_tokens = cache_tokens = 1
    session_id = "s"


def add_attempt(engine, key, number, *, outcome, commit=None, cost=True, check=True):
    with get_session(engine) as session:
        run = story_runs.run_by_id(session, RUN)
        assert run is not None
        sub = rows.sub_task_row(session, run.id, key, "small", [])
        attempt = rows.start_attempt(
            session, sub, number, f"agent-attempt/{key}-{number}", "w", NOW
        )
        agent = rows.start_agent_run(session, attempt, "builder", "sonnet", "low", "s", NOW)
        rows.finish_agent_run(session, agent, Reply() if cost else None, error=None, now=NOW)
        rows.record_checks(
            session, attempt, sub, [("tests", check, "$ npm test\nexit 1, 2.0s\n" + "x" * 900)]
        )
        attempt.commit_sha = commit
        rows.finish_attempt(
            session, attempt, sub, outcome=outcome, reason=None, stage="judge", status="done",
            now=NOW,
        )  # fmt: skip
        if outcome == "done" and commit:
            merge_rows.record_merge(
                session, attempt, sub, kind="fast-forward", commit=commit, tests_passed=True,
                now=NOW,
            )  # fmt: skip


@pytest.fixture
def world(tmp_path):
    repo, config, engine = build_project(tmp_path, prepared=False)
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", f"agent/{RUN}")
    git(repo, "checkout", "-q", f"agent/{RUN}")
    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "SMT-62")
    merged = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "side", base)
    (repo / "b.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "SMT-63")
    loose = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    with get_session(engine) as session:
        run = story_runs.run_by_id(session, RUN)
        assert run is not None
        run.branch = f"agent/{RUN}"
    add_attempt(engine, "SMT-62", 1, outcome="done", commit=merged)
    add_attempt(engine, "SMT-63", 1, outcome="done", commit=loose, check=False)
    return repo, engine, merged, loose


def test_the_facts_come_from_the_database_git_and_the_plan(world):
    repo, engine, merged, _ = world
    facts = collect_facts(engine, repo, RUN)
    assert (facts.story_key, facts.branch) == ("SMT-61", f"agent/{RUN}")
    first = facts.tasks[0]
    assert first.key == "SMT-62" and first.status == "done" and first.attempts[0].commit == merged
    files = first.attempts[0].files
    assert files is not None
    assert [(c.path, c.added, c.deleted) for c in files] == [("a.txt", 2, 0)]
    assert first.attempts[0].checks[0].passed and first.attempts[0].agents[0].cost_usd == 0.25


def test_git_decides_what_is_merged(world):
    repo, engine, _, _ = world
    facts = collect_facts(engine, repo, RUN)
    assert facts.tasks[0].attempts[0].merged is True
    assert facts.tasks[1].attempts[0].merged is False
    assert facts.merged_files() == ["a.txt"]


def test_the_cost_is_the_sum_of_what_the_agents_cost(world):
    repo, engine, _, _ = world
    facts = collect_facts(engine, repo, RUN)
    assert facts.agent_cost_usd == 0.5 and facts.total_cost_usd == 0.5


def test_an_attempt_without_a_commit_has_no_files(tmp_path):
    repo, _, engine = build_project(tmp_path, prepared=False)
    add_attempt(engine, "SMT-62", 1, outcome="failed", commit=None, cost=False)
    attempt = collect_facts(engine, repo, RUN).tasks[0].attempts[0]
    assert attempt.merged is None and attempt.files is None and attempt.agents[0].cost_usd is None


def test_a_commit_git_cannot_show_is_reported_not_guessed(tmp_path):
    repo, _, engine = build_project(tmp_path, prepared=False)
    add_attempt(engine, "SMT-62", 1, outcome="done", commit="0" * 40)
    attempt = collect_facts(engine, repo, RUN).tasks[0].attempts[0]
    assert attempt.files is None and attempt.merged is False
    assert "Git cannot show it" in format_facts(collect_facts(engine, repo, RUN))


def test_a_run_with_a_plan_but_no_database_row_is_refused(tmp_path):
    repo, _, _ = approved_project(tmp_path)
    with pytest.raises(FactsError, match="not in the database"):
        collect_facts(init_db(make_engine(tmp_path / "empty.db")), repo, RUN)


def test_a_run_without_a_plan_is_refused(world):
    repo, engine, _, _ = world
    with pytest.raises(PlanFileError):
        collect_facts(engine, repo, "SMT-61-20990101-ffff")


def test_the_facts_file_is_written_in_the_run_folder(world):
    repo, engine, _, _ = world
    path = write_facts(repo, collect_facts(engine, repo, RUN))
    assert path == facts_path(repo, RUN) and path.is_file()
    assert "total_cost_usd" in path.read_text(encoding="utf-8")


def test_the_text_names_each_task_file_and_cost(world):
    repo, engine, _, _ = world
    text = format_facts(collect_facts(engine, repo, RUN))
    assert "SMT-62  done" in text and "file a.txt  +2 -0" in text
    assert "check tests: FAILED" in text and "Merged files: a.txt" in text


def test_a_check_names_its_command_even_when_the_output_is_long(world):
    repo, engine, _, _ = world
    text = format_facts(collect_facts(engine, repo, RUN))
    assert "check tests: FAILED  $ npm test (exit 1, 2.0s)" in text
