"""Planning from the command line, for the project and Jira space in .env:

python -m pipeline.planning plan SMT-56 [--budget 12] [--skip-tests]
    check, plan and save a story; --budget is dollars for planning and building it together
python -m pipeline.planning replan <run_id> --changes "your idea" [--budget 12] [--skip-tests]
    a new plan from an earlier one; the earlier one is kept and marked replaced
python -m pipeline.planning approve <run_id>
    write the plan's new dependencies to Jira as "is blocked by" links
python -m pipeline.planning show <run_id>
    print a saved plan again

Exit codes: 0 done, 1 could not read, plan or approve, 2 a readiness check failed.
"""

import argparse
import sys
from pathlib import Path

from core.settings import Settings, get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from core.trackers.jira.story import read_story
from core.trackers.models import Story
from pipeline.planning.approval import ApprovalError, approve_plan
from pipeline.planning.plan_file import PlanFileError, load_plan, plan_path
from pipeline.planning.plan_view import format_plan
from pipeline.planning.planner import NotReady, PlanningError, PlanResult, plan_story
from pipeline.planning.readiness import format_checks
from pipeline.planning.replan import replan_story
from pipeline.runner.claude_runner import AgentRunner, ClaudeCliRunner
from pipeline.workspace.git import GitError, repository_root

HANDLED = (GitError, PlanFileError, ApprovalError, TrackerError, ValueError)


def project_root(settings: Settings) -> Path:
    if settings.project_path is None:
        raise GitError("BRIGADE_PROJECT_PATH is empty in .env.")
    return repository_root(settings.project_path)


def fetch_story(key: str, settings: Settings) -> Story:
    client = JiraClient.from_settings(settings)
    try:
        return read_story(client, key, settings.jira_project_key or None)
    finally:
        client.close()


def finish(make_result) -> int:
    """Run a planning call and print its plan, or why there is none."""
    try:
        result: PlanResult = make_result()
    except NotReady as exc:
        print(format_checks(exc.checks))
        return 2
    except PlanningError as exc:
        print(f"Not planned: {exc}", file=sys.stderr)
        return 1
    print(format_plan(result.record, result.path))
    return 0


def plan(args: argparse.Namespace, settings: Settings, runner: AgentRunner) -> int:
    try:
        story = fetch_story(args.story, settings)
    except TrackerError as exc:
        print(f"Could not read {args.story}: {exc}", file=sys.stderr)
        return 1
    print(f"Planning {args.story}. The Planner reads the project; this takes a few minutes.")
    return finish(
        lambda: plan_story(
            story, settings, runner, run_tests=not args.skip_tests, budget=args.budget
        )
    )


def replan(args: argparse.Namespace, settings: Settings, runner: AgentRunner) -> int:
    try:
        key = load_plan(project_root(settings), args.run_id)["source"]["key"]
        story = fetch_story(key, settings)
    except HANDLED as exc:
        print(f"Cannot re-plan {args.run_id}: {exc}", file=sys.stderr)
        return 1
    print(f"Re-planning {key} from {args.run_id}. This takes a few minutes.")
    return finish(
        lambda: replan_story(
            story,
            settings,
            runner,
            args.run_id,
            args.changes,
            run_tests=not args.skip_tests,
            budget=args.budget,
        )
    )


def approve(args: argparse.Namespace, settings: Settings) -> int:
    try:
        root = project_root(settings)
        client = JiraClient.from_settings(settings)
        try:
            record = approve_plan(root, args.run_id, client, settings.jira_project_key or None)
        finally:
            client.close()
    except HANDLED as exc:
        print(f"Not approved: {exc}", file=sys.stderr)
        return 1
    approval = record["approval"]
    print(f"Approved {args.run_id} ({record['source']['key']}) at {approval['approved_at']}.")
    for link in approval["written"]:
        print(f"  written: {link['subtask']} is blocked by {link['blocked_by']} (with a comment)")
    for link in approval["already_in_jira"]:
        print(f"  already in Jira: {link['subtask']} is blocked by {link['blocked_by']}")
    if not approval["written"] and not approval["already_in_jira"]:
        print("  no new links: every dependency was already in Jira.")
    return 0


def show(args: argparse.Namespace, settings: Settings) -> int:
    try:
        root = project_root(settings)
        record = load_plan(root, args.run_id)
    except HANDLED as exc:
        print(f"Cannot show {args.run_id}: {exc}", file=sys.stderr)
        return 1
    print(format_plan(record, plan_path(root, args.run_id)))
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="python -m pipeline.planning")
    commands = top.add_subparsers(dest="command", required=True)

    def planning_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--skip-tests", action="store_true", help="skip the test run first")
        command.add_argument(
            "--budget", type=float, help="dollars for planning and building the story"
        )

    one = commands.add_parser("plan", help="check, plan and save a story")
    one.add_argument("story", help="the story's Jira key, such as SMT-56")
    planning_options(one)
    again = commands.add_parser("replan", help="a new plan from an earlier one")
    again.add_argument("run_id")
    again.add_argument("--changes", required=True, help="what should change: your own idea")
    planning_options(again)
    commands.add_parser("approve", help="write the new dependencies to Jira").add_argument("run_id")
    commands.add_parser("show", help="print a saved plan").add_argument("run_id")
    return top


def main(argv: list[str] | None = None, runner: AgentRunner | None = None) -> int:
    args = parser().parse_args(argv)
    settings = get_settings()
    if args.command == "show":
        return show(args, settings)
    if args.command == "approve":
        return approve(args, settings)
    run = runner or ClaudeCliRunner()
    return (plan if args.command == "plan" else replan)(args, settings, run)


if __name__ == "__main__":
    raise SystemExit(main())
