"""A fingerprint of the files a worktree differs in, to tell what an agent wrote in between.

The Tester is not stopped from writing outside the test folders (Claude Code on Windows ignores
Edit and Write allow rules), so what it wrote is measured after it ends: take the fingerprints
before and after, and the paths whose fingerprint changed are what it wrote.
"""

import hashlib
from pathlib import Path

from pipeline.workspace.git import changed_paths

GONE = "(not a file)"


def fingerprints(root: Path) -> dict[str, str]:
    """Every file that differs from HEAD, with a hash of its content ('(not a file)' if deleted)."""
    prints: dict[str, str] = {}
    for name in changed_paths(root):
        path = Path(root) / name
        try:
            prints[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else GONE
        except OSError:
            prints[name] = "(unreadable)"
    return prints


def written_between(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Paths created, changed, deleted or restored to HEAD between two fingerprint sets."""
    return sorted(name for name in {*before, *after} if before.get(name) != after.get(name))
