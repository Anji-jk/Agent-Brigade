"""A documentation task end to end, with a fake agent for each of the two documentation agents."""

import json

import pytest

from core.db import get_session
from core.db.models import AgentRun
from core.db.repositories import merge_rows
from core.files.atomic import write_json_atomic
from core.runs import run_directory
from pipeline.control import task_control as tc
from pipeline.planning.plan_file import load_plan, plan_path
from pipeline.runner.claude_runner import AgentReply
from pipeline.stages import checkpoint, interrupt, task_run
from pipeline.stages.judge_report import write_judge_report
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import team_project
from tests.pipeline.workspace.repo import git

KEY = "SMT-62"
DOC = "# Notes\nThe toggle saves the choice.\n"
REPORT = "**Wrote:** docs/a.md\n**Left out:** nothing\n**Not tested:** nothing"


def verdict(status="supported", evidence="facts show it", line=2, **more):
    data = {
        "verdict": "pass" if status == "supported" else "fail",
        "claims": [{"file": "docs/a.md", "line": line, "claim": "saves", "status": status,
                    "evidence": evidence}],
        "criteria": [{"criterion": 1, "met": True, "evidence": "lines 1-2"}],
        "problems": [],
    }  # fmt: skip
    data.update(more)
    return json.dumps(data)


class DocRunner:
    """Plays both documentation agents. `reviews`: the Reviewer's answers in turn (last repeats)."""

    def __init__(self, reviews=None, writes=None, errors=None):
        self.reviews = list(reviews or [verdict()])
        self.writes = {"docs/a.md": DOC} if writes is None else writes
        self.errors = errors or {}
        self.requests = []

    def of(self, agent):
        return [r for r in self.requests if r.agent == agent]

    def run(self, request):
        self.requests.append(request)
        if request.agent in self.errors:
            from pipeline.runner.claude_runner import AgentError

            raise AgentError(self.errors[request.agent])
        if request.agent == "documenter":
            for name, text in self.writes.items():
                path = request.cwd / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            text = REPORT
        else:
            text = self.reviews.pop(0) if len(self.reviews) > 1 else self.reviews[0]
        return AgentReply(text, request.session_id, cost_usd=0.01, turns=2, duration_ms=1000)


@pytest.fixture
def world(tmp_path):
    repo, config, engine = team_project(tmp_path, files=("docs/a.md",))
    plan = load_plan(repo, RUN)
    plan["tasks"] = plan["tasks"][:1]  # the story's other work is not under test here
    plan["tasks"][0]["title"] = "Documentation: describe the toggle"
    write_json_atomic(plan_path(repo, RUN), plan)
    return repo, config, engine


def roles(engine):
    with get_session(engine) as session:
        return [(r.role, r.status) for r in session.query(AgentRun)]


def attempt(engine):
    with get_session(engine) as session:
        row = merge_rows.newest_attempt(session, RUN, KEY)
        return row[1] if row is not None else None


def test_a_documentation_task_runs_two_agents_and_never_the_builder(world):
    repo, config, engine = world
    runner = DocRunner()
    result = task_run.run_task(settings=config, run_id=RUN, key=KEY, runner=runner, engine=engine)
    assert result.ok and result.built is None
    assert result.judged is not None and result.judged.outcome == "done"
    assert [r.agent for r in runner.requests] == ["documenter", "doc-reviewer"]
    assert roles(engine) == [("documenter", "done"), ("reviewer", "done")]
    assert checkpoint.completed(repo, RUN, KEY, 1) == ["builder", "checks", "tester"]
    assert "Documenter, attempt 1" in result.text and "\nDONE" in result.text


def test_a_pass_is_committed_with_the_documentation_and_recorded(world):
    repo, config, engine = world
    result = task_run.run_task(config, RUN, KEY, DocRunner(), engine=engine)
    assert result.judged is not None
    sha = result.judged.commit
    assert sha and git(repo, "show", f"{sha}:docs/a.md").startswith("# Notes")
    row = attempt(engine)
    assert row is not None
    assert (row.outcome, row.commit_sha) == ("done", sha)
    saved = run_directory(repo, RUN) / "judge" / f"{KEY}-1.json"
    assert saved.is_file() and json.loads(saved.read_text(encoding="utf-8"))["done"] is True


def test_a_false_sentence_sends_the_documenter_back_once_with_the_problem(world):
    _, config, engine = world
    runner = DocRunner(reviews=[verdict("unsupported", "no fact says it"), verdict()])
    result = task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert result.ok
    first, second = runner.of("documenter")
    assert "Feedback from the Documentation Reviewer" not in first.prompt
    assert "docs/a.md line 2 is unsupported: saves (no fact says it)" in second.prompt
    assert len(runner.of("doc-reviewer")) == 2


def test_a_second_failure_is_needs_review_and_nothing_is_committed(world):
    repo, config, engine = world
    bad = verdict("contradicted", "facts show 2 tasks")
    result = task_run.run_task(config, RUN, KEY, DocRunner(reviews=[bad]), engine=engine)
    assert not result.ok and result.judged is not None and result.judged.outcome == "needs_review"
    row = attempt(engine)
    assert result.judged.commit is None and row is not None and row.commit_sha is None
    assert "is contradicted" in result.judged.reasons[0]


def test_a_file_outside_the_list_goes_to_a_person_and_the_reviewer_is_not_paid(world):
    _, config, engine = world
    runner = DocRunner(writes={"docs/a.md": DOC, "README.md": "x"})
    result = task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert result.judged is not None
    assert result.judged.outcome == "needs_review" and runner.of("doc-reviewer") == []
    assert "does not list: README.md" in result.judged.reasons[0]


def test_a_documenter_that_writes_nothing_fails_the_attempt_for_a_new_one(world):
    _, config, engine = world
    runner = DocRunner(writes={})
    result = task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert result.judged is not None
    assert result.judged.outcome == "failed" and runner.of("doc-reviewer") == []
    assert "changed no files" in result.judged.feedback


def test_a_stop_before_the_task_starts_starts_no_agent(world):
    repo, config, engine = world
    tc.ask(run_directory(repo, RUN), KEY, tc.STOP)
    runner = DocRunner()
    with pytest.raises(interrupt.TaskInterrupted):
        task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert runner.requests == []


def test_continue_after_the_documenter_goes_straight_to_the_review(world):
    repo, config, engine = world
    runner = DocRunner(reviews=["not json at all"])
    task_run.run_task(config, RUN, KEY, runner, engine=engine)  # the Reviewer is unusable
    row = attempt(engine)
    assert row is not None
    assert row.outcome == "needs_review"
    again = DocRunner()
    result = task_run.run_task(config, RUN, KEY, again, engine=engine, resume=True)
    assert [r.agent for r in again.requests] == ["doc-reviewer"] and result.ok


def test_the_judge_record_of_a_failed_try_is_readable_by_the_next_attempt(world):
    repo, config, engine = world
    runner = DocRunner(writes={})
    result = task_run.run_task(config, RUN, KEY, runner, engine=engine)
    assert result.judged is not None
    path = write_judge_report(repo, result.judged)
    assert json.loads(path.read_text(encoding="utf-8"))["feedback"].startswith("- ")
