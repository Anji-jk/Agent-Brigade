"""Read-only Git questions about a project's checkout. Ported from Agent Lab (worktrees.py).

Phase 4 adds worktrees here; for now nothing in this module changes a repository.
"""

import re
import subprocess
from pathlib import Path

from pipeline.workspace.layout import OWN_BRANCH_PREFIXES

GIT_TIMEOUT_SECONDS = 60
_BASE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}")


class GitError(RuntimeError):
    """Git could not answer. The message is safe to show."""


def validate_base_ref(base_ref: str) -> str:
    """A branch name such as main or release/2.0; nothing Git could read as an option."""
    if (
        not isinstance(base_ref, str)
        or not _BASE_REF.fullmatch(base_ref)
        or ".." in base_ref
        or base_ref.endswith(("/", ".lock"))
    ):
        raise GitError(f"Invalid base branch: {base_ref!r} (BRIGADE_BASE_BRANCH in .env).")
    return base_ref


def run_git(folder: Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> str:
    """Run one git command in `folder` and return its output without the trailing newline."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(folder),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH.") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {args[0]} did not finish: {type(exc).__name__}") from exc
    if completed.returncode != 0:
        message = " ".join((completed.stderr or completed.stdout).split())[:300]
        raise GitError(f"git {args[0]} failed: {message}")
    return completed.stdout.rstrip("\n")


def repository_root(folder: Path) -> Path:
    """The top folder of the Git repository that holds `folder`."""
    if not Path(folder).is_dir():
        raise GitError(f"{folder} is not a folder (BRIGADE_PROJECT_PATH in .env).")
    try:
        top = run_git(Path(folder), "rev-parse", "--show-toplevel")
    except GitError as exc:
        raise GitError(f"{folder} is not inside a Git repository.") from exc
    return Path(top).resolve()


def commit_of(root: Path, ref: str) -> str | None:
    """The commit `ref` names, or None when it names none."""
    try:
        return run_git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except GitError:
        return None


def changed_files(root: Path) -> list[str]:
    """Uncommitted changes and untracked files, as `git status --porcelain` lists them."""
    return [line[3:].strip() for line in run_git(root, "status", "--porcelain").splitlines()]


def _status_paths(raw: str) -> list[str]:
    """Paths from `git status --porcelain=v1 -z`; a rename lists the new name, then the old one."""
    parts = raw.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(parts):
        entry = parts[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if ("R" in entry[:2] or "C" in entry[:2]) and index < len(parts):
            paths.append(parts[index])
            index += 1
    return paths


def changed_paths(root: Path) -> list[str]:
    """Every file that differs from HEAD, sorted: new files one by one, never as a folder.

    Unlike `changed_files` this is exact: names are not quoted and a new folder lists its files,
    so a rule about a path (such as a .env inside a new folder) cannot be missed.
    """
    raw = run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    noise = ("__pycache__", ".pytest_cache")
    return sorted(
        {path for path in _status_paths(raw) if not any(part in noise for part in path.split("/"))}
    )


def current_branch(root: Path) -> str:
    """The checked-out branch, or "" on a detached HEAD."""
    return run_git(root, "branch", "--show-current")


def head_commit(root: Path) -> str:
    return run_git(root, "rev-parse", "HEAD")


def _is_ours(branch: str) -> bool:
    return branch.startswith(OWN_BRANCH_PREFIXES)


def _foreign_branches(root: Path) -> str:
    names = run_git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
    return "\n".join(name for name in names if not _is_ours(name))


def _foreign_worktrees(root: Path) -> str:
    """`git worktree list`, without the worktrees of the orchestrator's own branches."""
    kept = []
    for block in run_git(root, "worktree", "list", "--porcelain").split("\n\n"):
        branch = next((x for x in block.splitlines() if x.startswith("branch refs/heads/")), "")
        if not _is_ours(branch.removeprefix("branch refs/heads/")):
            kept.append(block)
    return "\n\n".join(kept)


def repository_state(root: Path) -> dict[str, str]:
    """Everything a read-only agent must leave as it was: changes, HEAD, branches, worktrees.

    The orchestrator's own branches and worktrees are left out: with tasks running in parallel,
    it sets up, commits and merges the others while one agent runs, and that is not the agent's
    doing.
    """
    return {
        "status": run_git(root, "status", "--porcelain"),
        "head": run_git(root, "rev-parse", "HEAD"),
        "branches": _foreign_branches(root),
        "worktrees": _foreign_worktrees(root),
    }


def tracked_files(root: Path, limit: int) -> str:
    """The tracked file paths, one per line, cut at about `limit` characters with a note."""
    listing = run_git(root, "ls-files")
    if len(listing) <= limit:
        return listing or "(no tracked files)"
    kept = listing[: limit + 1].rsplit("\n", 1)[0]  # whole lines only
    total, shown = listing.count("\n") + 1, kept.count("\n") + 1
    return f"{kept}\n... ({total - shown} more files not listed; use Glob to find them)"
