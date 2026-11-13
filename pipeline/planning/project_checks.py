"""The checkout, project-file and test checks: run against the project folder."""

from pathlib import Path

from pipeline.planning.check_model import FAILED, OK, WARNING, Check, plural
from pipeline.planning.project_check import check_project
from pipeline.workspace import commands, git

NO_TESTS_EXIT_CODE = 5  # pytest's code for "collected nothing"
TESTS_PASS = "The project's tests pass on the base branch"


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


# ---------- Project and tests ----------


def check_project_files(folder: Path, docs_dir: str) -> list[Check]:
    """CLAUDE.md and the docs folder: warnings only, a project with less still plans."""
    return [
        Check("Project", OK if finding.found else WARNING, finding.what)
        for finding in check_project(folder, docs_dir)
    ]


def check_tests(folder: Path, configured: str, timeout: int) -> Check:
    """Run the project's tests where the checkout stands (on the base branch)."""
    command = commands.project_test_command(folder, configured)
    result = commands.run_command(command, folder, timeout=timeout)
    shown = " ".join(command)
    if result.passed:
        return Check("Tests", OK, TESTS_PASS, f"{shown} ({result.seconds:.0f}s)")
    if result.timed_out:
        return Check(
            "Tests",
            FAILED,
            TESTS_PASS,
            f"{shown} did not finish in {timeout}s (BRIGADE_TEST_TIMEOUT in .env).",
        )
    if result.exit_code == NO_TESTS_EXIT_CODE and "pytest" in command:
        return Check(
            "Tests",
            WARNING,
            "The project has tests",
            "pytest found none, so a sub-task is judged only on its own new tests.",
        )
    last = (result.output_tail.strip().splitlines() or [""])[-1][:200]
    code = "could not start" if result.exit_code is None else f"exit code {result.exit_code}"
    return Check(
        "Tests",
        FAILED,
        TESTS_PASS,
        f"{shown} ended with {code}: {last} (BRIGADE_TEST_COMMAND in .env sets the command).",
    )
