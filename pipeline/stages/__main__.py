"""The build stages from the command line, for the project in .env:

python -m pipeline.stages prepare <run_id>
    story branch, story worktree, the plan's setup lines, then the baseline checks
python -m pipeline.stages attempt <run_id> <KEY> [--number 1]
    a fresh worktree for one attempt of one sub-task, with the setup lines run in it
python -m pipeline.stages build <run_id> <KEY> [--number 1]
    one Builder run for one sub-task in its own worktree (spends money, within its size's cap)
python -m pipeline.stages check <run_id> <KEY> [--number 1]
    measure what the Builder left (changed files, protected paths, files outside the task's
    Files) and run the task's Verify lines in its worktree; no agent, no cost
python -m pipeline.stages test <run_id> <KEY> [--number 1]
    the Tester writes unit tests for the criteria (skipped when the task has no place for tests),
    then the Verify lines run again (spends money, within its size's cap)
python -m pipeline.stages judge <run_id> <KEY> [--number 1]
    the Reviewer reads the change, code decides Done, Failed or Needs review, and a Done attempt
    is committed in its worktree (spends money, within its size's cap)
python -m pipeline.stages task <run_id> <KEY> [--number 1]
    build, check, test and judge in one go
python -m pipeline.stages ready <run_id> <KEY>
    may this sub-task start now? Its dependencies must be merged, and no task that may touch the
    same files may be running (free; exit 0 ready, 2 not ready)
python -m pipeline.stages merge <run_id> <KEY> [--number N]
    merge the Done attempt (default: the newest) into the story branch: fast-forward, or a real
    merge whose combined code is checked first. No agent, no cost. A conflict or a failing check
    leaves the story branch as it was and fails the attempt
python -m pipeline.stages retry <run_id> <KEY>
    the next attempt of a Failed sub-task, in a fresh worktree from the story tip, with the
    feedback of the failed one: build, check, test and judge (spends money). At most
    BRIGADE_MAX_RETRIES retries (.env)
python -m pipeline.stages story <run_id>
    the whole story: every task built, merged and retried until none can move, up to
    BRIGADE_MAX_PARALLEL tasks at once when the plan allows it (spends money, within each task's
    cap). Run it again to resume: merged tasks cost nothing. Writes story-events.jsonl and
    story-report.json in the run's folder, and each attempt's events in attempts/<KEY>-<n>/;
    one loop per run at a time
python -m pipeline.stages loop <run_id>
    what the Start button runs: prepare the run if it is not prepared yet (a failed setup stops
    it, a baseline that already fails is only reported), then the story loop as above
python -m pipeline.stages jira-mirror <run_id>
    make Jira show where a finished run ended (statuses, labels, comments), from its story
    report. The build does this itself after every step; use this when Jira was unreachable or
    a status name was wrong (JIRA_STATUS_* in .env). Writes only to Jira; no agent, no cost
python -m pipeline.stages rows <run_id>
    the sub_tasks, attempts, agent_runs and checks rows the builds of this run wrote
python -m pipeline.stages clean <run_id> [--discard]
    remove the run's worktrees (branches stay); --discard also drops uncommitted changes
python -m pipeline.stages reset <run_id>
    start the run over: forget the attempts and rows its builds wrote and the report folders,
    keeping plan.json. Refused until clean has removed the worktrees and the run's branches
    are deleted (it lists them); no agent, no cost

Exit codes: 0 done, 1 refused or could not start, 2 a setup or baseline line FAILED, the
Builder stopped with an error, a blocking check failed, or the decision is not Done.
"""

import argparse
import sys

from core.db import get_engine, init_db
from core.settings import get_settings
from core.trackers.errors import TrackerError
from pipeline.jira_sync.catch_up import catch_up
from pipeline.planning.plan_file import PlanFileError
from pipeline.runner.claude_runner import AgentError, AgentRunner, ClaudeCliRunner
from pipeline.stages.builder_report import format_build, write_build_report
from pipeline.stages.builder_rows import format_rows
from pipeline.stages.builder_run import build_attempt
from pipeline.stages.check_report import format_checks, write_check_report
from pipeline.stages.check_run import check_attempt
from pipeline.stages.errors import BuildError
from pipeline.stages.judge_report import format_judge, write_judge_report
from pipeline.stages.judge_run import judge_attempt
from pipeline.stages.loop_start import start_loop
from pipeline.stages.merge_report import format_merge, write_merge_report
from pipeline.stages.merge_run import merge_attempt
from pipeline.stages.prepare import (
    PrepareError,
    approved_plan,
    clean_run,
    prepare_attempt,
    prepare_story,
    project_root,
)
from pipeline.stages.prepare_report import format_attempt, format_prepared
from pipeline.stages.reset import reset_run
from pipeline.stages.retry import next_attempt_number, previous_feedback
from pipeline.stages.schedule import start_blockers
from pipeline.stages.story_loop import run_story
from pipeline.stages.task_run import run_task
from pipeline.stages.tester_report import format_tester, write_tester_result
from pipeline.stages.tester_run import run_tester
from pipeline.workspace.git import GitError

HANDLED = (PrepareError, BuildError, AgentError, PlanFileError, GitError, TrackerError, ValueError)


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
    check = commands.add_parser("check", help="measure a built attempt and run its Verify lines")
    check.add_argument("run_id")
    check.add_argument("key", help="the sub-task's Jira key, such as SMT-62")
    check.add_argument("--number", type=int, default=1, help="attempt number, from 1")
    for name, text in (
        ("test", "the Tester writes tests, then the Verify lines run again"),
        ("judge", "the Reviewer, the decision and the commit"),
        ("task", "build, check, test and judge one sub-task"),
    ):
        stage = commands.add_parser(name, help=text)
        stage.add_argument("run_id")
        stage.add_argument("key", help="the sub-task's Jira key, such as SMT-62")
        stage.add_argument("--number", type=int, default=1, help="attempt number, from 1")
    for name, text in (
        ("ready", "may this sub-task start now?"),
        ("retry", "the next attempt of a Failed sub-task, with the feedback"),
    ):
        stage = commands.add_parser(name, help=text)
        stage.add_argument("run_id")
        stage.add_argument("key", help="the sub-task's Jira key, such as SMT-62")
    merge = commands.add_parser("merge", help="merge a Done attempt into the story branch")
    merge.add_argument("run_id")
    merge.add_argument("key", help="the sub-task's Jira key, such as SMT-62")
    merge.add_argument("--number", type=int, default=None, help="attempt number (default newest)")
    commands.add_parser("jira-mirror", help="make Jira match a finished run").add_argument("run_id")
    commands.add_parser("story", help="build and merge every task of the story").add_argument(
        "run_id"
    )
    commands.add_parser("loop", help="prepare if needed, then the story loop").add_argument(
        "run_id"
    )
    commands.add_parser("reset", help="forget the builds of the run, keep its plan").add_argument(
        "run_id"
    )
    commands.add_parser("rows", help="the database rows the builds wrote").add_argument("run_id")
    clean = commands.add_parser("clean", help="remove the run's worktrees; branches stay")
    clean.add_argument("run_id")
    clean.add_argument("--discard", action="store_true", help="also drop uncommitted changes")
    return top


def run_flow(args: argparse.Namespace, settings, runner: AgentRunner) -> int | None:
    """ready, merge, retry, story and loop: what happens between attempts. None: not one of them."""
    if args.command == "ready":
        root = project_root(settings)
        plan = approved_plan(root, args.run_id)
        reasons = start_blockers(root, plan, args.run_id, args.key, init_db(None))
        if reasons:
            print(f"{args.key} cannot start yet:")
            print("\n".join(f"- {text}" for text in reasons))
            return 2
        print(f"{args.key} may start: its dependencies are merged and nothing overlaps it.")
        return 0
    if args.command == "merge":
        merged = merge_attempt(settings, args.run_id, args.key, args.number)
        path = write_merge_report(project_root(settings), merged)
        print(format_merge(merged, path))
        return 0 if merged.merged else 2
    if args.command == "jira-mirror":
        problems = catch_up(settings, args.run_id)
        print("\n".join(problems) if problems else "Jira shows where the run ended.")
        return 2 if problems else 0
    if args.command == "story":
        story = run_story(settings, args.run_id, runner)
        print(story.text())
        return 0 if story.ok else 2
    if args.command == "loop":
        started = start_loop(settings, args.run_id, runner)
        print("\n".join(started.warnings + [started.story.text()]))
        return 0 if started.story.ok else 2
    if args.command == "retry":
        number = next_attempt_number(init_db(None), args.run_id, args.key, settings.max_retries)
        told = previous_feedback(project_root(settings), args.run_id, args.key, number)
        print(f"Attempt {number} of {args.key}: the Builder is told:")
        print("\n".join(f"  | {text}" for text in (told or "(nothing)").split("\n")))
        done = run_task(settings, args.run_id, args.key, runner, number)
        print(done.text)
        return 0 if done.ok else 2
    return None


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
        if args.command == "check":
            checked = check_attempt(settings, args.run_id, args.key, args.number)
            path = write_check_report(project_root(settings), args.run_id, checked)
            print(format_checks(checked, args.run_id, path))
            return 0 if checked.passed else 2
        if args.command == "test":
            tested = run_tester(settings, args.run_id, args.key, runner, args.number)
            path = write_tester_result(project_root(settings), tested)
            print(format_tester(tested, path))
            return 0 if tested.ok and not tested.problems else 2
        if args.command == "judge":
            judged = judge_attempt(settings, args.run_id, args.key, runner, args.number)
            path = write_judge_report(project_root(settings), judged)
            print(format_judge(judged, path))
            return 0 if judged.done else 2
        if args.command == "task":
            done = run_task(settings, args.run_id, args.key, runner, args.number)
            print(done.text)
            return 0 if done.ok else 2
        flow = run_flow(args, settings, runner)
        if flow is not None:
            return flow
        if args.command == "rows":
            print(format_rows(get_engine(), args.run_id))
            return 0
        if args.command == "reset":
            done = reset_run(settings, args.run_id)
            print(done.text())
            return 2 if done.kept else 0
        print("\n".join(clean_run(settings, args.run_id, discard_changes=args.discard)))
        return 0
    except HANDLED as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
