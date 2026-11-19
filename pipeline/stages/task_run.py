"""One sub-task end to end: Builder, checks, Tester, Reviewer, decision, commit.

run_task   the stages in order, each writing its own report, so that any of them can also be run
           alone. It stops early only where a later stage would be wasted: the Builder failed,
           or a blocking check failed (the Tester is skipped, then judge decides without asking
           the Reviewer). The retry of a Failed attempt and the merge are the next steps (4.5).

A person's Stop or Cancel (pipeline.stages.interrupt) is looked for before every stage and after
a stage that was cut short; it raises TaskInterrupted. Each stage that ends well is written to
the attempt's checkpoint, so that Continue does not pay for it again.

``resume=True`` is Continue: the same attempt goes on from its first unfinished stage. A stage
that finished before the stop is not run again (its report is on disk and the judge reads it
there); the stage that was cut short is run again, from the start, in the same worktree.
"""

from dataclasses import dataclass

from sqlalchemy import Engine

from core.db import init_db
from core.settings import Settings
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages import checkpoint
from pipeline.stages.attempt_log import AttemptLog
from pipeline.stages.attempt_resume import reopen_rows
from pipeline.stages.builder_report import BuildResult, format_build, write_build_report
from pipeline.stages.builder_run import build_attempt
from pipeline.stages.check_report import format_checks, write_check_report
from pipeline.stages.check_run import check_attempt
from pipeline.stages.interrupt import (
    StopAware,
    agent_file_of,
    guard,
    stop_file_of,
    stop_for_limit,
)
from pipeline.stages.judge_report import JudgeResult, format_judge, write_judge_report
from pipeline.stages.judge_run import judge_attempt
from pipeline.stages.prepare import project_root
from pipeline.stages.tester_report import TesterResult, format_tester, write_tester_result
from pipeline.stages.tester_run import run_tester


@dataclass
class TaskResult:
    text: str  # every stage's printout, in order
    built: BuildResult | None  # None: the Builder finished before a stop and was not run again
    judged: JudgeResult | None = None
    tested: TesterResult | None = None

    @property
    def ok(self) -> bool:
        return self.judged is not None and self.judged.done


def run_task(
    settings: Settings, run_id: str, key: str, runner: AgentRunner, number: int = 1,
    engine: Engine | None = None, *, resume: bool = False,
) -> TaskResult:  # fmt: skip
    """Build, check, test and judge attempt `number` of `key`.

    TaskInterrupted: a person stopped or cancelled it (the state is already recorded)."""
    root = project_root(settings)
    engine = init_db(engine)
    runner = StopAware(
        runner,
        stop_file_of(root, run_id, key),
        agent_file_of(root, run_id, key),
        on_limit=lambda message: stop_for_limit(root, run_id, key, message),
    )
    log = AttemptLog(root, run_id, key, number)
    done = checkpoint.completed(root, run_id, key, number) if resume else []
    first = checkpoint.resume_stage(root, run_id, key, number) if resume else "builder"

    def look(resume_at: str, finished: bool = False) -> None:
        guard(engine, root, run_id, key, number, resume_at, finished=finished)

    log.emit("attempt_continued" if resume else "attempt_started", attempt=number, stage=first)
    parts: list[str] = []
    built = None
    if "builder" in done:
        reopen_rows(engine, run_id, key, number, first)
        parts.append("Builder: finished before the stop; not run again.")
    else:
        look("builder")
        built = build_attempt(settings, run_id, key, runner, number, engine, resume=resume)
        parts.append(format_build(built, write_build_report(root, built)))
        if not built.ok:
            look("builder")
            return TaskResult("\n\n".join(parts), built)
        checkpoint.save(root, run_id, key, number, "builder")
    if "checks" in done:
        parts.append("Checks: finished before the stop; not run again.")
    else:
        look("checks")
        checked = check_attempt(settings, run_id, key, number, engine)
        parts.append(format_checks(checked, run_id, write_check_report(root, run_id, checked)))
        log.emit("checks_finished", passed=checked.passed, failures=checked.failures())
        checkpoint.save(root, run_id, key, number, "checks")
    tested = None
    if "tester" in done:
        parts.append("Tester: finished before the stop; not run again.")
        look("judge")
    else:
        look("tester")
        tested = run_tester(settings, run_id, key, runner, number, engine)
        parts.append(format_tester(tested, write_tester_result(root, tested)))
        if tested.ok:
            checkpoint.save(root, run_id, key, number, "tester")
        look("judge" if tested.ok else "tester")
    judged = judge_attempt(settings, run_id, key, runner, number, engine)
    parts.append(format_judge(judged, write_judge_report(root, judged)))
    look("judge", finished=judged.done)
    return TaskResult("\n\n".join(parts), built, judged, tested)
