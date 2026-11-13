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

from core.settings import Settings, get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from core.trackers.jira.story import read_story
from core.trackers.models import Story
from pipeline.planning.check_model import (
    FAILED,
    GROUPS,
    LABELS,
    OK,
    SKIPPED,
    WARNING,
    Check,
    StoryCheck,
    plural,
)
from pipeline.planning.project_checks import (
    TESTS_PASS,
    check_checkout,
    check_project_files,
    check_tests,
)
from pipeline.planning.story_checks import check_story

# The checks live in check_model, story_checks and project_checks; they are named here too,
# because this is the module the rest of the code (and python -m) uses.
__all__ = [
    "FAILED",
    "OK",
    "SKIPPED",
    "WARNING",
    "Check",
    "StoryCheck",
    "check_checkout",
    "check_project_files",
    "check_story",
    "check_tests",
    "format_checks",
    "main",
    "run_checks",
]


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
        f"{plural(failed, 'check')} failed; nothing was planned. "
        "Fix the lines marked FAIL and check again."
        if failed
        else "Ready to plan."
    )
    if warnings:
        lines.append(
            f"{plural(warnings, 'warning')} (--): they stop nothing; "
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
