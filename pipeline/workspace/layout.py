"""The names of one run's branches and worktrees.

A run has one story branch, ``agent/<run_id>``, and one branch per sub-task attempt,
``agent-attempt/<run_id>/<KEY>-<n>``. The attempt branches are NOT under ``agent/<run_id>/``:
Git cannot hold a branch ``agent/X`` and a branch ``agent/X/Y`` at the same time.

Worktrees live under one root (BRIGADE_WORKTREE_ROOT, a short path such as ``C:\\bw``, since
``node_modules`` paths are long and Windows stops at 260 characters)::

    <root>/<run_id>/story        merges and the combined tests of the story branch
    <root>/<run_id>/<KEY>-<n>    attempt n of one sub-task, a fresh one for every attempt
"""

from pathlib import Path

from core.runs import STORY_KEY_PATTERN, validate_run_id


def _key(key: str) -> str:
    if not isinstance(key, str) or not STORY_KEY_PATTERN.fullmatch(key):
        raise ValueError(f"Not a Jira key: {key!r}")
    return key


def _number(number: int) -> int:
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError(f"An attempt number starts at 1, not {number!r}")
    return number


def story_branch(run_id: str) -> str:
    return f"agent/{validate_run_id(run_id)}"


def attempt_branch(run_id: str, key: str, number: int) -> str:
    return f"agent-attempt/{validate_run_id(run_id)}/{_key(key)}-{_number(number)}"


def run_worktrees(root: Path, run_id: str) -> Path:
    """The folder that holds every worktree of the run."""
    return Path(root) / validate_run_id(run_id)


def story_worktree(root: Path, run_id: str) -> Path:
    return run_worktrees(root, run_id) / "story"


def attempt_worktree(root: Path, run_id: str, key: str, number: int) -> Path:
    return run_worktrees(root, run_id) / f"{_key(key)}-{_number(number)}"
