"""Merge one attempt's commit into the story branch, in the story worktree.

Only the story worktree is touched, and the story branch only moves when a merge is finished:

is_ancestor   is a commit already part of a branch (this is how "merged" is answered)
fast_forward  move the story branch to the commit; only when the story tip is part of its history
begin_merge   a real merge that is not committed yet, so the combined code can be checked first
abort_merge   undo it: the story branch and its files are as they were
finish_merge  commit the checked merge as 'Agent Brigade'

A conflict aborts by itself and raises MergeConflict with the files in conflict.
"""

from pathlib import Path

from pipeline.workspace.commit import AUTHOR_EMAIL, AUTHOR_NAME, commit_staged
from pipeline.workspace.git import GitError, head_commit, run_git

# git merge needs a committer identity even with --no-commit; a machine (or CI) may have none.
IDENTITY = ("-c", f"user.name={AUTHOR_NAME}", "-c", f"user.email={AUTHOR_EMAIL}")


class MergeConflict(GitError):
    def __init__(self, files: list[str]):
        self.files = files
        shown = ", ".join(files[:10]) or "unknown files"
        super().__init__(f"The merge conflicts in: {shown}.")


def is_ancestor(root: Path, commit: str, ref: str) -> bool:
    """True when `commit` is part of the history of `ref` (or is the same commit)."""
    try:
        run_git(root, "merge-base", "--is-ancestor", commit, ref)
    except GitError:
        return False
    return True


def tracked_changes(worktree: Path) -> list[str]:
    """Edits to tracked files and staged changes; untracked files (build output) are ignored."""
    out = run_git(worktree, "status", "--porcelain", "--untracked-files=no")
    return [line[3:] for line in out.splitlines()]


def fast_forward(worktree: Path, commit: str) -> str:
    """Move the checked-out story branch to `commit`; the new tip."""
    run_git(worktree, "merge", "--ff-only", commit)
    return head_commit(worktree)


def abort_merge(worktree: Path) -> None:
    try:
        run_git(worktree, "merge", "--abort")
    except GitError:
        pass  # no merge was in progress


def begin_merge(worktree: Path, commit: str) -> None:
    """Merge `commit` without committing. On a conflict: abort and raise MergeConflict."""
    try:
        run_git(worktree, *IDENTITY, "merge", "--no-ff", "--no-commit", commit)
    except GitError as exc:
        conflicts = run_git(worktree, "diff", "--name-only", "--diff-filter=U").splitlines()
        abort_merge(worktree)
        if conflicts:
            raise MergeConflict(conflicts) from None
        raise exc


def finish_merge(worktree: Path, subject: str) -> str:
    """Commit the merge that begin_merge left. Returns the new tip."""
    return commit_staged(worktree, subject)
