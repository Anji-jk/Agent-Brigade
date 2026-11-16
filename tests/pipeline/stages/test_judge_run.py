import pytest

from core.db import get_session
from core.db.models import AgentRun, Attempt, SubTask
from pipeline.stages import builder_run as b
from pipeline.stages import judge_report as jr
from pipeline.stages import judge_run as j
from pipeline.stages import tester_report as tr
from pipeline.stages import tester_run as t
from tests.pipeline.stages.stage_setup import FAIL, OK, RUN, line
from tests.pipeline.stages.team_setup import (
    TeamRunner,
    answer_of_reviewer,
    answer_of_tester,
    built_and_checked,
    team_project,
)
from tests.pipeline.workspace.repo import git


def judge(repo, config, engine, runner):
    """The stages in order, as `task` runs them. Returns the decision."""
    built_and_checked(repo, config, engine, runner)
    tested = t.run_tester(config, RUN, "SMT-62", runner, engine=engine)
    tr.write_tester_result(repo, tested)
    return j.judge_attempt(config, RUN, "SMT-62", runner, engine=engine)


def worktree(tmp_path):
    return tmp_path / "bw" / RUN / "SMT-62-1"


def rows(engine):
    with get_session(engine) as session:
        attempt = session.query(Attempt).one()
        sub = session.query(SubTask).one()
        roles = [r.role for r in session.query(AgentRun).order_by(AgentRun.id)]
        return attempt.outcome, attempt.commit_sha, sub.status, sub.current_stage, roles


def test_a_good_attempt_is_done_and_committed_with_exactly_its_files(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner()
    result = judge(repo, config, engine, runner)
    assert result.outcome == "done" and result.commit and result.left_over == []
    wt = worktree(tmp_path)
    assert git(wt, "rev-parse", "HEAD") == result.commit
    assert git(wt, "log", "-1", "--format=%an|%s") == "Agent Brigade|SMT-62: Do T1"
    assert git(wt, "show", "--stat", "--format=", "HEAD").count("|") == 2
    assert git(wt, "status", "--porcelain") == ""
    assert "Acceptance criteria:\n- It works." in git(wt, "log", "-1", "--format=%B")
    assert rows(engine) == ("done", result.commit, "done", "decision",
                            ["builder", "tester", "reviewer"])  # fmt: skip
    text = jr.format_judge(result, jr.write_judge_report(repo, result))
    assert "DONE" in text and "met     1. It works." in text and "evidence 1" in text
    assert "Committed: " in text and "(not merged yet)" in text


def test_an_attempt_that_is_already_committed_is_not_judged_again(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner()
    done = judge(repo, config, engine, runner)
    before, reviewers = rows(engine), len(runner.of("reviewer"))
    with pytest.raises(b.BuildError, match="already Done and committed"):
        j.judge_attempt(config, RUN, "SMT-62", runner, engine=engine)
    assert rows(engine) == before and rows(engine)[1] == done.commit  # the Done record is kept
    assert len(runner.of("reviewer")) == reviewers  # and the Reviewer was not paid again
    assert git(worktree(tmp_path), "rev-parse", "HEAD") == done.commit


def test_a_failing_new_check_fails_the_attempt_whatever_the_reviewer_says(tmp_path):
    repo, config, engine = team_project(tmp_path, verify=(OK, FAIL))
    runner = TeamRunner()  # the Reviewer says pass
    result = judge(repo, config, engine, runner)
    assert result.outcome == "failed" and result.commit is None and len(runner.of("reviewer")) == 1
    assert any("failed (exit 3)" in reason for reason in result.reasons)
    assert "Attempt 1 of this task" in result.feedback and "clean checkout" in result.feedback
    assert rows(engine)[:3] == ("failed", None, "error")
    assert git(worktree(tmp_path), "log", "--oneline").count("\n") == 1  # no new commit


def test_a_check_that_already_failed_at_baseline_is_left_to_the_reviewer(tmp_path):
    repo, config, engine = team_project(tmp_path, verify=(FAIL,), checks=(FAIL,))
    runner = TeamRunner()
    result = judge(repo, config, engine, runner)
    assert result.outcome == "done" and any("also failed before" in n for n in result.notes)
    prompt = runner.of("reviewer")[0].prompt
    assert "also failed before the Builder" in prompt and "Output before the Builder" in prompt


def test_the_reviewer_failing_a_criterion_fails_the_attempt_with_its_evidence(tmp_path):
    repo, config, engine = team_project(tmp_path, criteria=("A", "B"))
    said = answer_of_reviewer((True, False), problems=("src/a.py ignores B",))
    tester = answer_of_tester({1: ["tests/test_new.py"], 2: ["tests/test_new.py"]})
    result = judge(repo, config, engine, TeamRunner(reviewer_text=said, tester_text=tester))
    assert result.outcome == "failed" and result.commit is None
    assert (
        "Not met: B (evidence 2)" in result.reasons
        and "Reviewer: src/a.py ignores B" in result.reasons
    )
    assert "NOT MET 2. B" in jr.format_judge(result)


def test_an_unusable_reviewer_answer_sends_the_attempt_to_a_person(tmp_path):
    repo, config, engine = team_project(tmp_path, criteria=("A", "B"))
    said = answer_of_reviewer((True,))  # skips criterion 2, twice
    tester = answer_of_tester({1: ["tests/test_new.py"], 2: ["tests/test_new.py"]})
    result = judge(repo, config, engine, TeamRunner(reviewer_text=said, tester_text=tester))
    assert result.outcome == "needs_review" and result.commit is None
    assert "The Reviewer did not finish" in result.reasons[0] and "criteria: 2" in result.reasons[0]
    assert rows(engine)[0] == "needs_review"


def test_a_reviewer_that_edits_a_file_is_not_believed(tmp_path):
    repo, config, engine = team_project(tmp_path)
    result = judge(repo, config, engine, TeamRunner(reviewer={"src/a.py": "x = 99\n"}))
    assert result.outcome == "needs_review" and "read-only" in result.reasons[0]


def test_nothing_changed_or_a_protected_path_fails_without_paying_the_reviewer(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(builder={})
    result = judge(repo, config, engine, runner)
    assert result.outcome == "failed" and result.reasons == ["The Builder changed no files."]
    assert runner.of("tester") == [] and runner.of("reviewer") == []
    assert "Reviewer skipped" in jr.format_judge(result)
    repo, config, engine = team_project(tmp_path / "two")
    runner = TeamRunner(builder={"CLAUDE.md": "new rules", "src/a.py": "x"})
    result = judge(repo, config, engine, runner)
    assert result.outcome == "failed" and "CLAUDE.md" in result.reasons[0]
    assert runner.of("reviewer") == [] and result.commit is None


def test_a_tester_that_wrote_a_non_test_file_fails_the_attempt_but_the_reviewer_still_runs(
    tmp_path,
):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(tester={"tests/test_new.py": "x", "src/a.py": "x = 2\n"})
    result = judge(repo, config, engine, runner)
    assert result.outcome == "failed" and len(runner.of("reviewer")) == 1
    assert any("not tests" in reason for reason in result.reasons)


def test_a_tester_that_did_not_finish_sends_the_attempt_to_a_person_unpaid_reviewer(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner(errors={"tester": "ran out of budget"})
    result = judge(repo, config, engine, runner)
    assert result.outcome == "needs_review" and "ran out of budget" in result.reasons[0]
    assert runner.of("reviewer") == [] and result.commit is None


def test_a_file_a_check_left_behind_is_reported_and_not_committed(tmp_path):
    leave = line("open('leftover.log', 'w').write('x')")
    repo, config, engine = team_project(tmp_path, verify=(leave,))
    result = judge(repo, config, engine, TeamRunner())
    assert result.outcome == "done" and result.left_over == ["leftover.log"]
    assert "leftover.log" not in git(worktree(tmp_path), "show", "--stat", "--format=", "HEAD")
    assert git(worktree(tmp_path), "status", "--porcelain") == "?? leftover.log"


def test_without_a_test_place_the_reviewer_alone_decides_and_says_so(tmp_path):
    repo, config, engine = team_project(tmp_path, old_test=False)
    runner = TeamRunner()
    result = judge(repo, config, engine, runner)
    assert result.outcome == "done" and runner.of("tester") == []
    assert "No Tester ran for this task." in runner.of("reviewer")[0].prompt
    assert git(worktree(tmp_path), "show", "--stat", "--format=", "HEAD").count("|") == 1


def test_judging_needs_a_built_and_checked_attempt(tmp_path):
    repo, config, engine = team_project(tmp_path)
    with pytest.raises(b.BuildError, match="build it first"):
        j.judge_attempt(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    b.build_attempt(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    with pytest.raises(b.BuildError, match="run check first"):
        j.judge_attempt(config, RUN, "SMT-62", TeamRunner(), engine=engine)
