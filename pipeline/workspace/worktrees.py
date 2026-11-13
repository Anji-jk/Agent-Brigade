"""Create, list and remove Git worktrees. Ported from Agent Lab (worktrees.py), split up.

Safety rules kept here, whatever the caller asks:

* the main checkout is never removed, and neither is a folder Git does not know as a worktree;
* a branch is never deleted, so the work of a cancelled or failed attempt stays reachable;
* a worktree with uncommitted changes is never removed, unless the caller passes
  ``discard_changes=True``: a separate, explicit decision;
* a failed step reports what it left behind; it does not delete things to hide the failure.

Only the Git data of the project changes (branches, worktree records). Its own files and its
checked-out branch are never touched.
"""

from dataclasses import dataclass
from pathlib import Path

from pipeline.workspace.git import GitError, changed_files, commit_of, run_git


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    head: str
    branch: str  # "" on a detached HEAD


def branch_exists(root: Path, branch: str) -> bool:
    return commit_of(root, f"refs/heads/{branch}") is not None


def create_branch(root: Path, branch: str, commit: str) -> None:
    """A new branch at `commit`. It must not exist: a run is prepared once."""
    if branch_exists(root, branch):
        raise GitError(f"The branch {branch} already exists.")
    run_git(root, "branch", "--", branch, commit)


def list_worktrees(root: Path) -> list[WorktreeInfo]:
    """Every worktree of the repository; the first is the main checkout."""
    found: list[WorktreeInfo] = []
    for block in run_git(root, "worktree", "list", "--porcelain").split("\n\n"):
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        if "worktree" in fields:
            branch = fields.get("branch", "").removeprefix("refs/heads/")
            found.append(WorktreeInfo(Path(fields["worktree"]), fields.get("HEAD", ""), branch))
    return found


def _free(path: Path) -> Path:
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise GitError(f"{path} already exists and is not empty.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def add_story_worktree(root: Path, path: Path, branch: str) -> None:
    """A worktree on an existing branch."""
    run_git(root, "worktree", "add", str(_free(path)), branch)


def add_attempt_worktree(root: Path, path: Path, branch: str, start: str) -> None:
    """A worktree on a NEW branch that starts at the commit `start`."""
    if branch_exists(root, branch):
        raise GitError(f"The branch {branch} already exists.")
    run_git(root, "worktree", "add", "-b", branch, str(_free(path)), start)


def remove_worktree(root: Path, path: Path, *, discard_changes: bool = False) -> None:
    """Remove one worktree (its folder and its Git record), keeping its branch."""
    path = Path(path).resolve()
    known = list_worktrees(root)
    if not known or path == known[0].path.resolve():
        raise GitError(f"{path} is the main checkout; it is never removed.")
    if path not in {info.path.resolve() for info in known}:
        raise GitError(f"{path} is not a worktree of this project; nothing was removed.")
    if path.is_dir():
        changes = changed_files(path)
        if changes and not discard_changes:
            raise GitError(
                f"{path} has {len(changes)} uncommitted or untracked file(s) "
                f"(first: {changes[0]}); nothing was removed."
            )
    run_git(root, "worktree", "remove", *(["--force"] if discard_changes else []), str(path))
