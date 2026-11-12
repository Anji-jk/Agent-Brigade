"""A small real Git repository for tests that need one."""

import subprocess
from pathlib import Path


def git(folder: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def make_repo(folder: Path, branch: str = "main") -> Path:
    """A repository with one commit on `branch`."""
    folder.mkdir(parents=True, exist_ok=True)
    git(folder, "init", "-q")
    git(folder, "checkout", "-q", "-b", branch)
    (folder / "README.md").write_text("hello\n", encoding="utf-8")
    git(folder, "add", "README.md")
    git(folder, "commit", "-q", "-m", "first")
    return folder
