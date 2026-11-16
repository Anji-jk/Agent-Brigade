"""Stage exactly the files an attempt changed and commit them, as Brigade and never as an agent.

Agents never touch Git. When an attempt is judged Done, the orchestrator stages the paths it
measured (never ``git add .``, so a stray file a check left behind is not swept in) and commits
in the attempt's own worktree. Hooks are skipped (--no-verify): the project's checks have
already run, and a person's pre-commit hook must not decide what Brigade commits.
"""

from pathlib import Path

from pipeline.workspace.git import run_git

AUTHOR_NAME = "Agent Brigade"
AUTHOR_EMAIL = "agent-brigade@localhost"
SUBJECT_CHARS = 120


def stage_paths(root: Path, paths: list[str]) -> None:
    """Make the index hold exactly these paths, deletions included, and nothing else.

    Anything staged earlier is unstaged first (the files stay as they are), so a file a check
    left behind and an earlier stage staged cannot ride along into the commit.
    """
    run_git(root, "reset", "-q")
    if paths:
        run_git(root, "--literal-pathspecs", "add", "-A", "--", *paths)


def staged_diff(root: Path, *, context: int = 3) -> str:
    """The staged changes against HEAD as text; new files are shown in full."""
    return run_git(root, "diff", "--cached", "--no-color", "--no-ext-diff", f"-U{context}")


def commit_message(key: str, title: str, criteria: list[str]) -> tuple[str, str]:
    """(subject, body): '<KEY>: <title>', then the acceptance criteria the task had."""
    subject = f"{key}: {' '.join(title.split())}"
    if len(subject) > SUBJECT_CHARS:
        subject = subject[: SUBJECT_CHARS - 1].rstrip() + "…"
    body = "Acceptance criteria:\n" + "\n".join(f"- {' '.join(c.split())}" for c in criteria)
    return subject, body if criteria else ""


def commit_staged(root: Path, subject: str, body: str = "") -> str:
    """Commit what is staged, author and committer 'Agent Brigade'. Returns the commit id."""
    args = ["-c", f"user.name={AUTHOR_NAME}", "-c", f"user.email={AUTHOR_EMAIL}"]
    args += ["-c", "commit.gpgsign=false", "commit", "--no-verify", "-m", subject]
    if body:
        args += ["-m", body]
    run_git(root, *args)
    return run_git(root, "rev-parse", "HEAD")
