"""What preparing a run did, as records, as text and as ``build/prepare.json``.

Each setup or baseline line becomes a StepResult: ok, failed, or warning. The one warning is
pytest's exit code 5 ("no tests collected"): a project that has no tests yet is not a broken
one. Nothing else is judged by name.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import run_directory, utc_now
from pipeline.workspace.commands import CommandResult

NO_TESTS_EXIT_CODE = 5  # pytest's code for "collected nothing"
OK, WARNING, FAILED = "ok", "warning", "failed"


@dataclass(frozen=True)
class StepResult:
    line: str
    status: str
    exit_code: int | None
    seconds: float
    output_tail: str


def step_result(result: CommandResult) -> StepResult:
    line = result.command
    if result.passed:
        status = OK
    elif result.exit_code == NO_TESTS_EXIT_CODE and "pytest" in line:
        status = WARNING
    else:
        status = FAILED
    tail = result.output_tail
    if result.timed_out:
        tail += f"\nStopped: it did not finish in {round(result.seconds)}s (BRIGADE_TEST_TIMEOUT)."
    return StepResult(line, status, result.exit_code, round(result.seconds, 1), tail)


@dataclass
class Prepared:
    run_id: str
    branch: str
    base_commit: str
    story_worktree: str
    setup: list[StepResult] = field(default_factory=list)
    baseline: list[StepResult] = field(default_factory=list)
    leftovers: list[str] = field(default_factory=list)  # files the baseline left in the worktree
    prepared_at: str = field(default_factory=utc_now)

    @property
    def ok(self) -> bool:
        return all(step.status != FAILED for step in (*self.setup, *self.baseline))


@dataclass
class AttemptReady:
    run_id: str
    key: str
    number: int
    branch: str
    start_commit: str
    worktree: str
    setup: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(step.status != FAILED for step in self.setup)


def write_report(project_root: Path, prepared: Prepared) -> Path:
    path = run_directory(project_root, prepared.run_id) / "build" / "prepare.json"
    data: dict[str, Any] = asdict(prepared)
    data["ok"] = prepared.ok
    write_json_atomic(path, data)
    return path


def step_lines(title: str, steps: list[StepResult]) -> list[str]:
    out = [title] if steps else [f"{title} none listed in the plan"]
    for step in steps:
        code = "did not finish" if step.exit_code is None else f"exit {step.exit_code}"
        out.append(f"  {step.status.upper():<7} {step.line}  ({code}, {step.seconds}s)")
        if step.status != OK and step.output_tail.strip():
            last = step.output_tail.strip().splitlines()[-1][:200]
            out.append(f"          {last}")
    return out


def format_prepared(prepared: Prepared, report: Path | None = None) -> str:
    lines = [
        f"Run {prepared.run_id}",
        f"Branch:    {prepared.branch} at {prepared.base_commit[:12]}",
        f"Worktree:  {prepared.story_worktree}",
        *step_lines("Setup:", prepared.setup),
        *step_lines("Baseline (the project's own checks, before any agent):", prepared.baseline),
    ]
    if prepared.leftovers:
        lines.append(
            f"Warning: the baseline left {len(prepared.leftovers)} changed or new file(s) in "
            f"the story worktree (first: {prepared.leftovers[0]}). Ignore them in the "
            "project's .gitignore, or merges into this worktree will be refused."
        )
    lines.append("Ready for agents." if prepared.ok else "Not ready: fix the FAILED lines first.")
    if report:
        lines.append(f"Report:    {report}")
    return "\n".join(lines)


def format_attempt(ready: AttemptReady) -> str:
    return "\n".join(
        [
            f"Attempt {ready.number} of {ready.key} in run {ready.run_id}",
            f"Branch:    {ready.branch} at {ready.start_commit[:12]} (the story branch tip)",
            f"Worktree:  {ready.worktree}",
            *step_lines("Setup:", ready.setup),
            "Ready for the Builder." if ready.ok else "Not ready: fix the FAILED lines first.",
        ]
    )
