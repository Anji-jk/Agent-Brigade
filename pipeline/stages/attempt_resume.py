"""Going on with an attempt that was stopped, instead of making a new one.

An attempt is a worktree, a branch, its reports (keyed by its number) and its database row. A
stopped attempt already has all four, and the Builder's unfinished work is in the worktree, so
Continue uses them as they are: nothing is copied and no retry is spent. A new attempt would
start from the story tip and lose that work.

resume_ready   the worktree and branch of the attempt, checked to still be there
resume_note    what the Builder is told when it goes on in a worktree that holds earlier work
reopen_rows    the attempt's row and its task's row go back to running
"""

from pathlib import Path

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories import attempt_rows, merge_rows
from core.settings import Settings
from pipeline.stages.errors import BuildError
from pipeline.stages.prepare import project_root
from pipeline.stages.prepare_report import AttemptReady
from pipeline.workspace import layout
from pipeline.workspace.git import commit_of

RESUME_NOTE = """\
Your earlier session on this task was stopped before it finished. Its work is still in this
worktree, uncommitted: run `git status` and `git diff` first and see what is already done.
Go on from there. Do not start over, do not undo it, and do not repeat what is finished.
Then check the whole task against its criteria, as you always do."""


def resume_ready(settings: Settings, run_id: str, key: str, number: int) -> AttemptReady:
    """The attempt's worktree and branch as they are. BuildError: either is gone."""
    root = project_root(settings)
    branch = layout.attempt_branch(run_id, key, number)
    path = layout.attempt_worktree(settings.worktrees_dir, run_id, key, number)
    tip = commit_of(root, f"refs/heads/{branch}")
    if tip is None or not Path(path).is_dir():
        raise BuildError(
            f"Attempt {number} of {key} cannot be continued: its "
            f"{'branch' if tip is None else 'worktree'} is gone. Cancel it, then build it again."
        )
    return AttemptReady(run_id, key, number, branch, tip, str(path))


def resume_note(number: int, earlier_feedback: str) -> str:
    """The Builder's feedback for a continued attempt: what it must know, then the old feedback
    of the attempt before it (a retry that is continued still has to fix what failed)."""
    return "\n\n".join(part for part in (RESUME_NOTE, earlier_feedback.strip()) if part)


def reopen_rows(engine: Engine, run_id: str, key: str, number: int, stage: str) -> int:
    """Put the attempt's rows back to running; returns the attempt row's id.
    BuildError: the database has no such attempt."""
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, run_id, key)
        if found is None or found[1].number != number:
            raise BuildError(f"{key} has no attempt {number} in run {run_id} to continue.")
        sub, attempt = found
        attempt_rows.reopen_attempt(session, attempt, sub, stage)
        return attempt.id
