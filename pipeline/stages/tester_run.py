"""The Tester stage of one attempt: unit tests for the criteria, then the Verify lines again.

run_tester   start the Tester in the attempt worktree (skipped, with the reason, when there is
             no place for tests), measure what it wrote and which tests it named, then run
             the task's Verify lines again so that they run its tests

The Tester is told to write only test files, but cannot be stopped, so what it wrote is measured
by fingerprinting the worktree before and after. A failing Verify line afterwards is a fact for
decide(), not an error here. Nothing is committed.
"""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import Engine

from core.db import get_session, init_db
from core.db.models import AgentRun
from core.db.repositories import attempt_rows, judge_rows
from core.settings import Settings
from pipeline.checks.agent_reports import parse_tester
from pipeline.checks.measure import verify_lines
from pipeline.checks.testfiles import (
    files_that_lost_tests,
    listed_test_paths,
    named_test_problems,
    writes_outside_tests,
)
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages.agent_ask import Asked, ask_for_report, usage_of
from pipeline.stages.agent_requests import limits, tester_request
from pipeline.stages.attempt_log import AttemptLog, agent_events_path
from pipeline.stages.builder_run import BuildError
from pipeline.stages.stage_inputs import Inputs, load_inputs
from pipeline.stages.tester_place import find_place
from pipeline.stages.tester_prompt import tester_prompt
from pipeline.stages.tester_report import TesterResult
from pipeline.workspace.commands import run_command
from pipeline.workspace.commit import stage_paths, staged_diff
from pipeline.workspace.git import changed_paths, repository_state, run_git
from pipeline.workspace.snapshot import fingerprints, written_between


def _skip_reason(inputs: Inputs) -> str | None:
    if inputs.check is None:
        raise BuildError(f"There is no check report for {inputs.key}: run check first.")
    if not inputs.check.get("passed"):
        return "a blocking check failed (nothing changed, or a protected path changed)."
    tracked = run_git(inputs.worktree, "ls-files").splitlines()
    place = find_place(
        inputs.worktree, inputs.task.get("files", []), [*tracked, *inputs.check["changed"]]
    )
    return None if place.found else place.reason()


def _ask(inputs: Inputs, runner: AgentRunner, session_id: str) -> tuple[Asked, list[str]]:
    """Run the Tester. (its answer, the paths it wrote). An error also when the project changed."""
    before, project = fingerprints(inputs.worktree), repository_state(inputs.root)
    changed = (inputs.check or {}).get("changed", [])
    prompt = tester_prompt(
        inputs.task, inputs.plan["commands"], changed, (inputs.build or {}).get("report", "")
    )
    events = agent_events_path(inputs.root, inputs.run_id, inputs.key, inputs.number, "tester")
    request = tester_request(
        inputs.task, inputs.plan["commands"], prompt, inputs.worktree, inputs.root, session_id,
        events_file=events,
    )  # fmt: skip
    count = len(inputs.criteria)
    asked = ask_for_report(runner, request, lambda text: parse_tester(text, count))
    if repository_state(inputs.root) != project:
        asked.error = (
            "The project's own folder changed while the Tester ran: look at git status in it."
        )
    return asked, written_between(before, fingerprints(inputs.worktree))


def _measure(result: TesterResult, inputs: Inputs, asked: Asked, wrote: list[str]) -> None:
    """Fill the result with the Tester's report and what code measured about it."""
    result.wrote = wrote
    result.outside = writes_outside_tests(wrote)
    mine = {*(inputs.check or {}).get("changed", []), *wrote}
    stage_paths(inputs.worktree, [p for p in changed_paths(inputs.worktree) if p in mine])
    result.weakened = files_that_lost_tests(staged_diff(inputs.worktree, context=0))
    report = asked.report
    if report is None:
        return
    result.summary, result.suspected_defects, result.notes = (
        report.summary, report.suspected_defects, report.notes,
    )  # fmt: skip
    result.coverage = {str(n): tests for n, tests in sorted(report.coverage.items())}
    result.uncovered = {str(n): why for n, why in sorted(report.uncovered.items())}
    names = [name for tests in report.coverage.values() for name in tests]
    listed = bool(listed_test_paths(inputs.task.get("files", [])))
    # A stated reason for each criterion is enough, unless the task itself lists a test file.
    result.no_tests = not names and (listed or not report.uncovered)
    result.invalid = named_test_problems(names, wrote)
    result.unnamed = [
        n for n in range(1, len(inputs.criteria) + 1)
        if not report.coverage.get(n) and n not in report.uncovered
    ]  # fmt: skip


def run_tester(
    settings: Settings, run_id: str, key: str, runner: AgentRunner, number: int = 1,
    engine: Engine | None = None,
) -> TesterResult:  # fmt: skip
    """Run the Tester stage. BuildError: nothing built or checked yet."""
    inputs = load_inputs(settings, run_id, key, number)
    result = TesterResult(run_id, key, number, limits=limits(inputs.task, "tester"))
    log = AttemptLog(inputs.root, run_id, key, number)
    result.skipped = _skip_reason(inputs)
    if result.skipped:
        log.emit("tester_finished", ran=False, skipped=result.skipped)
        return result
    engine, session_id = init_db(engine), str(uuid.uuid4())
    with get_session(engine) as session:
        sub, attempt = judge_rows.rows_of_attempt(session, run_id, key, number)
        row = attempt_rows.start_agent_run(
            session, attempt, "tester", result.limits["model"], result.limits["effort"],
            session_id, datetime.now(UTC),
        )  # fmt: skip
        judge_rows.set_stage(session, sub, "tester")
        row_id = row.id
    result.ran = True
    log.emit("tester_started", model=result.limits["model"], session_id=session_id)
    asked, wrote = _ask(inputs, runner, session_id)
    _measure(result, inputs, asked, wrote)
    result.error, result.usage = asked.error, usage_of(asked.reply)
    if result.error is None:  # run the Verify lines again, now that the Tester's tests exist
        lines = verify_lines(inputs.task)
        result.verify = [
            asdict(run_command(line, inputs.worktree, timeout=settings.test_timeout))
            for line in lines
        ]
    with get_session(engine) as session:
        row = session.get(AgentRun, row_id)
        if row is not None:
            attempt_rows.finish_agent_run(
                session, row, asked.reply, error=result.error, now=datetime.now(UTC)
            )
    log.emit(
        "tester_finished", ran=True, error=result.error, wrote=len(wrote), **(result.usage or {})
    )
    return result
