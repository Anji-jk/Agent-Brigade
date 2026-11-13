"""The checks that look at the project folder: its checkout, and its CLAUDE.md and docs."""

from pathlib import Path

from pipeline.planning.check_model import FAILED, OK, WARNING, Check, plural
from pipeline.planning.claude_md_check import check_project
from pipeline.workspace import git


def check_checkout(folder: Path, base_branch: str) -> list[Check]:
    """A clean checkout on the base branch: the plan must match what the build starts from."""
    try:
        root = git.repository_root(folder)
        base_branch = git.validate_base_ref(base_branch)
    except git.GitError as exc:
        return [Check("Checkout", FAILED, "The project folder is a Git repository", str(exc))]
    base = git.commit_of(root, base_branch)
    if base is None:
        return [
            Check(
                "Checkout",
                FAILED,
                f"The base branch {base_branch} exists",
                f"{base_branch!r} is not a branch here (BRIGADE_BASE_BRANCH in .env).",
            )
        ]
    found = [Check("Checkout", OK, f"The base branch {base_branch} exists", base[:12])]
    try:
        changes = git.changed_files(root)
        head, branch = git.head_commit(root), git.current_branch(root)
    except git.GitError as exc:
        return [*found, Check("Checkout", FAILED, "Git can read the checkout", str(exc))]
    found.append(
        Check(
            "Checkout",
            FAILED,
            "No uncommitted changes",
            f"{plural(len(changes), 'changed or new file')} (first: {changes[0]}). "
            "Commit or stash them first.",
        )
        if changes
        else Check("Checkout", OK, "No uncommitted changes")
    )
    on_base = head == base and branch == base_branch
    found.append(
        Check(
            "Checkout",
            FAILED,
            f"On {base_branch}",
            f"The checkout is on {branch or 'a detached HEAD'} at {head[:12]}, but {base_branch} "
            f"is {base[:12]}. Check out {base_branch} first.",
        )
        if not on_base
        else Check("Checkout", OK, f"On {base_branch}")
    )
    return found


# ---------- CLAUDE.md and docs ----------


def check_project_files(folder: Path, docs_dir: str) -> list[Check]:
    """CLAUDE.md and the docs folder: warnings only, a project with less still plans."""
    return [
        Check("Project", OK if finding.found else WARNING, finding.what)
        for finding in check_project(folder, docs_dir)
    ]
