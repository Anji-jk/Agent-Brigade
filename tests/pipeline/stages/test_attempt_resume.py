"""What Continue needs from an attempt: worktree, branch, rows, and the Builder's note."""

import pytest

from core.db import get_session
from core.db.repositories import merge_rows
from pipeline.stages.attempt_resume import RESUME_NOTE, reopen_rows, resume_note, resume_ready
from pipeline.stages.builder_run import build_attempt
from pipeline.stages.errors import BuildError
from pipeline.workspace import layout
from pipeline.workspace.worktrees import remove_worktree
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import TeamRunner, team_project

KEY = "SMT-62"


def test_the_ready_attempt_is_the_worktree_and_branch_it_already_has(tmp_path):
    repo, config, engine = team_project(tmp_path)
    built = build_attempt(config, RUN, KEY, TeamRunner(), 1, engine)
    ready = resume_ready(config, RUN, KEY, 1)
    assert (ready.branch, ready.worktree) == (built.branch, built.worktree)
    assert ready.setup == [] and ready.ok  # the setup lines ran once, when it was made


def test_a_missing_worktree_or_branch_is_said_plainly(tmp_path):
    repo, config, engine = team_project(tmp_path)
    with pytest.raises(BuildError, match="branch is gone"):
        resume_ready(config, RUN, KEY, 1)  # never built
    build_attempt(config, RUN, KEY, TeamRunner(), 1, engine)
    remove_worktree(
        repo, layout.attempt_worktree(config.worktrees_dir, RUN, KEY, 1), discard_changes=True
    )
    with pytest.raises(BuildError, match="worktree is gone"):
        resume_ready(config, RUN, KEY, 1)


def test_the_builders_note_comes_first_and_keeps_an_earlier_feedback(tmp_path):
    assert resume_note(1, "") == RESUME_NOTE
    both = resume_note(2, "  Fix the edge case.  ")
    assert both.startswith(RESUME_NOTE) and both.endswith("Fix the edge case.")


def test_reopening_puts_the_attempt_and_its_task_back_to_running(tmp_path):
    repo, config, engine = team_project(tmp_path)
    build_attempt(config, RUN, KEY, TeamRunner(), 1, engine)
    with get_session(engine) as session:
        sub, attempt = merge_rows.newest_attempt(session, RUN, KEY)
        attempt.outcome, attempt.reason, sub.status = "stopped", "Stopped by request", "stopped"
    attempt_id = reopen_rows(engine, RUN, KEY, 1, "tester")
    with get_session(engine) as session:
        sub, attempt = merge_rows.newest_attempt(session, RUN, KEY)
        assert attempt.id == attempt_id
        assert (attempt.outcome, attempt.reason, attempt.ended_at) == (None, None, None)
        assert (sub.status, sub.current_stage) == ("running", "tester")


def test_reopening_an_attempt_that_is_not_the_newest_is_refused(tmp_path):
    repo, config, engine = team_project(tmp_path)
    build_attempt(config, RUN, KEY, TeamRunner(), 1, engine)
    with pytest.raises(BuildError, match="no attempt 2"):
        reopen_rows(engine, RUN, KEY, 2, "builder")
    with pytest.raises(BuildError):
        reopen_rows(engine, RUN, "SMT-63", 1, "builder")
