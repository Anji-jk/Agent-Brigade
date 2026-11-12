"""The checks before a story is planned: is the story ready, and is the project?

Ported from Agent Lab (execution/story_check.py). Each check says ok, FAIL, a warning or
skipped, with what to fix. A failure stops planning, since the plan and the money spent on it
would be wasted; a warning only reports something that helps when filled in.

Story     it has sub-tasks and some are open; each open one has acceptance criteria; its text
          does not forbid the work; Jira's blocked-by links between the sub-tasks do not loop
Checkout  the base branch exists; the checkout has no uncommitted changes and is on that
          branch, so the plan matches what the build starts from
Project   CLAUDE.md has its structure, commands and rules; the docs folder exists (warnings)
Tests     the project's tests pass on the base branch; a project with no tests only warns

Nothing here writes anything or starts an agent. It reads Jira and Git, and runs the project's
own test command.

python -m pipeline.planning.readiness SMT-12 [--skip-tests]
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from core.settings import Settings, get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from core.trackers.jira.story import read_story
from core.trackers.models import Story
from pipeline.planning.project_check import check_project
from pipeline.planning.safety import prohibitions
from pipeline.workspace import commands, git

OK, FAILED, WARNING, SKIPPED = "ok", "failed", "warning", "skipped"
LABELS = {OK: "ok", FAILED: "FAIL", WARNING: "--", SKIPPED: "skip"}
GROUPS = ("Story", "Checkout", "Project", "Tests")
NO_TESTS_EXIT_CODE = 5  # pytest's code for "collected nothing"
TESTS_PASS = "The project's tests pass on the base branch"


@dataclass(frozen=True)
class Check:
    group: str
    status: str
    what: str
    detail: str = ""


@dataclass(frozen=True)
class StoryCheck:
    story_key: str
    checks: tuple[Check, ...]

    @property
    def failed(self) -> list[Check]:
        return [check for check in self.checks if check.status == FAILED]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.status == WARNING]

    @property
    def ready(self) -> bool:
        return not self.failed


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


# ---------- Story ----------


def _loops(story: Story) -> list[str]:
    """Open sub-tasks that are part of a cycle of blocked-by links."""
    waiting = {item.key: set(item.blocked_by) for item in story.open_subtasks()}
    for blockers in waiting.values():
        blockers.intersection_update(waiting)
    cyclic: set[str] = set()
    for start in waiting:
        pending, seen = list(waiting[start]), set()
        while pending:
            current = pending.pop()
            if current == start:
                cyclic.add(start)
                break
            if current not in seen:
                seen.add(current)
                pending.extend(waiting[current] - seen)
    return sorted(cyclic)


def check_story(story: Story) -> list[Check]:
    """The story and its sub-tasks, as Jira has them now."""
    key = story.story.key
    if not story.subtasks:
        return [Check("Story", FAILED, f"{key} has sub-tasks", "It has none: nothing to plan.")]
    found = [Check("Story", OK, f"{key} has {_plural(len(story.subtasks), 'sub-task')}")]
    open_items = story.open_subtasks()
    done = [item.key for item in story.subtasks if item.done]
    if not open_items:
        detail = "Every sub-task is Done in Jira; nothing is left to do."
        return [*found, Check("Story", FAILED, "Some sub-tasks are still open", detail)]
    left_out = f"Done in Jira and left out: {', '.join(done)}" if done else ""
    found.append(Check("Story", OK, f"{len(open_items)} open", left_out))

    what = "Every open sub-task has acceptance criteria"
    missing = [item.key for item in open_items if not item.acceptance_criteria]
    found.append(
        Check(
            "Story",
            FAILED,
            what,
            f'Missing in {", ".join(missing)}. Add an "Acceptance criteria:" part to their '
            "descriptions in Jira.",
        )
        if missing
        else Check("Story", OK, what)
    )

    what = "The text does not forbid the work"
    reasons = [
        f"{item.key} {reason}"
        for item in (story.story, *open_items)
        for reason in prohibitions(f"{item.summary}\n{item.description}")
    ]
    found.append(
        Check("Story", FAILED, what, "; ".join(reasons)) if reasons else Check("Story", OK, what)
    )

    what = "Jira's blocked-by links do not loop"
    looping = _loops(story)
    links = sum(len(item.blocked_by) for item in open_items)
    if looping:
        found.append(
            Check("Story", FAILED, what, f"These wait for each other: {', '.join(looping)}.")
        )
    else:
        detail = (
            f"{_plural(links, 'link')} between the sub-tasks"
            if links
            else "no links; the planner finds the order from the descriptions"
        )
        found.append(Check("Story", OK, what, detail))
    return found


# ---------- Checkout ----------


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
            f"{_plural(len(changes), 'changed or new file')} (first: {changes[0]}). "
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


def run_checks(story: Story, settings: Settings, *, run_tests: bool = True) -> StoryCheck:
    """All the checks, in order. The tests run only when the checkout is ready for them."""
    checks = check_story(story)
    folder = settings.project_path
    if folder is None:
        checks.append(
            Check("Checkout", FAILED, "A project folder is set", "BRIGADE_PROJECT_PATH is empty.")
        )
        checkout: list[Check] = checks[-1:]
    else:
        checkout = check_checkout(folder, settings.base_branch)
        checks += checkout
        checks += check_project_files(folder, settings.docs_dir)
    if not run_tests:
        checks.append(Check("Tests", SKIPPED, TESTS_PASS, "left out (--skip-tests)"))
    elif folder is None or any(check.status == FAILED for check in checkout):
        checks.append(Check("Tests", SKIPPED, TESTS_PASS, "the checkout is not ready"))
    else:
        checks.append(check_tests(folder, settings.test_command, settings.test_timeout))
    return StoryCheck(story.story.key, tuple(checks))


def format_checks(result: StoryCheck) -> str:
    lines = [f"Checks before planning {result.story_key}"]
    for group in GROUPS:
        mine = [check for check in result.checks if check.group == group]
        if not mine:
            continue
        lines.append(f"\n{group}")
        for check in mine:
            inline = check.detail and check.status == OK
            lines.append(
                f"  {LABELS[check.status]:<4} {check.what}"
                + (f"  ({check.detail})" if inline else "")
            )
            if check.detail and not inline:
                lines.append(f"       {check.detail}")
    lines.append("")
    failed, warnings = len(result.failed), len(result.warnings)
    lines.append(
        f"{_plural(failed, 'check')} failed; nothing was planned. "
        "Fix the lines marked FAIL and check again."
        if failed
        else "Ready to plan."
    )
    if warnings:
        lines.append(
            f"{_plural(warnings, 'warning')} (--): they stop nothing; "
            "filling them in helps the agents."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.planning.readiness")
    parser.add_argument("story", help="the story's Jira key, such as SMT-12")
    parser.add_argument("--skip-tests", action="store_true", help="do not run the project's tests")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        client = JiraClient.from_settings(settings)
        try:
            story = read_story(client, args.story, settings.jira_project_key or None)
        finally:
            client.close()
    except TrackerError as exc:
        print(f"Could not read {args.story}: {exc}", file=sys.stderr)
        return 1
    result = run_checks(story, settings, run_tests=not args.skip_tests)
    print(format_checks(result))
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
