"""`review`: only the Documentation Reviewer, on an attempt as it is now. Nothing is recorded."""

from core.db import get_session
from core.db.models import AgentRun, SubTask
from pipeline.documenting import __main__ as cli
from pipeline.documenting.doc_review_only import review_only
from pipeline.stages import task_run
from tests.pipeline.documenting.test_doc_task_run import KEY, DocRunner, attempt, verdict, world
from tests.pipeline.stages.stage_setup import RUN

__all__ = ["world"]  # the fixture, used here as it is in the task test


def stuck(config, engine):
    """An attempt that two failed reviews left at needs_review, with the document in place."""
    bad = verdict("contradicted", "facts show 2 tasks")
    task_run.run_task(config, RUN, KEY, DocRunner(reviews=[bad]), engine=engine)


def test_the_reviewer_alone_judges_the_document_as_it_is(world):
    _, config, engine = world
    stuck(config, engine)
    runner = DocRunner(reviews=[verdict()])
    done = review_only(config, RUN, KEY, runner, engine=engine)
    assert [r.agent for r in runner.requests] == ["doc-reviewer"]
    assert done.status == "done" and "DONE" in done.text


def test_a_false_sentence_is_reported_with_the_reason(world):
    _, config, engine = world
    stuck(config, engine)
    runner = DocRunner(reviews=[verdict("unsupported", "no fact says it")])
    done = review_only(config, RUN, KEY, runner, engine=engine)
    assert done.status != "done" and "line 2 is unsupported" in done.text


def test_nothing_is_committed_and_the_recorded_outcome_is_not_changed(world):
    _, config, engine = world
    stuck(config, engine)
    review_only(config, RUN, KEY, DocRunner(reviews=[verdict()]), engine=engine)
    row = attempt(engine)
    assert row is not None
    assert row.outcome == "needs_review" and row.commit_sha is None


def test_the_cost_of_the_review_is_recorded_as_an_agent_run(world):
    _, config, engine = world
    stuck(config, engine)
    with get_session(engine) as session:
        before = session.query(AgentRun).count()
    review_only(config, RUN, KEY, DocRunner(reviews=[verdict()]), engine=engine)
    with get_session(engine) as session:
        assert session.query(AgentRun).count() == before + 1


def test_the_command_prints_the_verdict_and_exits_by_it(world, monkeypatch, capsys):
    _, config, engine = world
    stuck(config, engine)
    monkeypatch.setattr(cli, "get_settings", lambda: config)
    monkeypatch.setattr(cli, "init_db", lambda _: engine)
    code = cli.main(["review", RUN, KEY], runner=DocRunner(reviews=[verdict()]))
    assert code == 0 and "DONE" in capsys.readouterr().out
    bad = DocRunner(reviews=[verdict("unsupported", "no fact says it")])
    assert cli.main(["review", RUN, KEY], runner=bad) == 2


def test_the_stage_word_of_the_task_is_put_back(world):
    _, config, engine = world
    stuck(config, engine)
    with get_session(engine) as session:
        before = session.query(SubTask).one().current_stage
        session.query(SubTask).one().current_stage = "merged"
    review_only(config, RUN, KEY, DocRunner(reviews=[verdict()]), engine=engine)
    with get_session(engine) as session:
        assert session.query(SubTask).one().current_stage == "merged" != before