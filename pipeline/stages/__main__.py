"""The build stages from the command line, for the project in .env:

python -m pipeline.stages prepare <run_id>
    story branch, story worktree, the plan's setup lines, then the baseline checks
python -m pipeline.stages attempt <run_id> <KEY> [--number 1]
    a fresh worktree for one attempt of one sub-task, with the setup lines run in it
python -m pipeline.stages build <run_id> <KEY> [--number 1]
    one Builder run for one sub-task in its own worktree (spends money, within its size's cap)
python -m pipeline.stages rows <run_id>
    the sub_tasks, attempts and agent_runs rows the builds of this run wrote
python -m pipeline.stages clean <run_id> [--discard]
    remove the run's worktrees (branches stay); --discard also drops uncommitted changes

Exit codes: 0 done, 1 refused or could not start, 2 a setup or baseline line FAILED or the
Builder stopped with an error.
"""

import argparse
import sys

from core.db import get_engine
from core.settings import get_settings
from pipeline.planning.plan_file import PlanFileError
from pipeline.runner.claude_runner import AgentError, AgentRunner, ClaudeCliRunner
from pipeline.stages.builder_report import format_build, write_build_report
from pipeline.stages.builder_rows import format_rows
from pipeline.stages.builder_run import BuildError, build_attempt
from pipeline.stages.prepare import (
    PrepareError,
    clean_run,
    prepare_attempt,
    prepare_story,
    project_root,
)
from pipeline.stages.prepare_report import format_attempt, format_prepared
from pipeline.workspace.git import GitError

HANDLED = (PrepareError, BuildError, AgentError, PlanFileError, GitError, ValueError)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="python -m pipeline.stages")
    commands = top.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="branch, worktree, setup and baseline").add_argument(
        "run_id"
    )
    attempt = commands.add_parser("attempt", help="a fresh worktree for one sub-task attempt")
    attempt.add_argument("run_id")
    attempt.add_argument("key", help="the sub-task's Jira key, such as SMT-62")
    attempt.add_argument("--number", type=int, default=1, help="attempt number, from 1")
    build = commands.add_parser("build", help="one Builder run for one sub-task")
    build.add_argument("run_id")
    build.add_argument("key", help="the sub-task's Jira key, such as SMT-64")
    build.add_argument("--number", type=int, default=1, help="attempt number, from 1")
    commands.add_parser("rows", help="the database rows the builds wrote").add_argument("run_id")
    clean = commands.add_parser("clean", help="remove the run's worktrees; branches stay")
    clean.add_argument("run_id")
    clean.add_argument("--discard", action="store_true", help="also drop uncommitted changes")
    return top


def main(argv: list[str] | None = None, runner: AgentRunner | None = None) -> int:
    args = parser().parse_args(argv)
    settings = get_settings()
    runner = runner or ClaudeCliRunner()
    try:
        if args.command == "prepare":
            prepared, report = prepare_story(settings, args.run_id)
            print(format_prepared(prepared, report))
            return 0 if prepared.ok else 2
        if args.command == "attempt":
            ready = prepare_attempt(settings, args.run_id, args.key, args.number)
            print(format_attempt(ready))
            return 0 if ready.ok else 2
        if args.command == "build":
            built = build_attempt(settings, args.run_id, args.key, runner, args.number)
            report = write_build_report(project_root(settings), built)
            print(format_build(built, report))
            return 0 if built.ok else 2
        if args.command == "rows":
            print(format_rows(get_engine(), args.run_id))
            return 0
        print("\n".join(clean_run(settings, args.run_id, discard_changes=args.discard)))
        return 0
    except HANDLED as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
