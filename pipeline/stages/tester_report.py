"""What the Tester stage found: a record, as text and as ``test/<KEY>-<n>.json``.

The record holds what the Tester said (its report) and what code measured about it: the files
it wrote, those that are not tests, the tests it weakened, the tests it named that cannot be
used, and the task's Verify lines run again with its tests in place. ``judge`` reads this file.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import utc_now
from pipeline.stages.stage_inputs import report_path

SHOWN = 30


@dataclass
class TesterResult:
    run_id: str
    key: str
    number: int
    limits: dict[str, Any] = field(default_factory=dict)
    ran: bool = False  # the Tester was started
    skipped: str | None = None  # why it was not started
    error: str | None = None  # why there is no usable answer (crash, timeout, unusable report)
    summary: str = ""
    coverage: dict[str, list[str]] = field(default_factory=dict)  # criterion -> tests
    uncovered: dict[str, str] = field(default_factory=dict)  # criterion -> reason
    suspected_defects: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    wrote: list[str] = field(default_factory=list)  # every path it created, changed or deleted
    outside: list[str] = field(default_factory=list)  # of those, not in a test location
    weakened: list[str] = field(default_factory=list)  # test files that lost a test or assertion
    invalid: list[str] = field(default_factory=list)  # named tests that cannot be used, and why
    unnamed: list[int] = field(default_factory=list)  # criteria with no test and no reason
    no_tests: bool = False
    verify: list[dict[str, Any]] = field(default_factory=list)  # the Verify lines run again
    usage: dict[str, Any] = field(default_factory=dict)
    finished_at: str = field(default_factory=utc_now)

    @property
    def ok(self) -> bool:
        """The Tester ended with a usable report, or was skipped on purpose."""
        return self.error is None

    @property
    def problems(self) -> bool:
        return bool(self.outside or self.weakened or self.invalid or self.unnamed or self.no_tests)


def write_tester_result(root: Path, result: TesterResult) -> Path:
    path = report_path(root, result.run_id, "test", result.key, result.number)
    data = asdict(result)
    data["ok"] = result.ok
    write_json_atomic(path, data)
    return path


def _names(paths: list[str]) -> str:
    more = f" ... and {len(paths) - SHOWN} more" if len(paths) > SHOWN else ""
    return ", ".join(paths[:SHOWN]) + more


def format_tester(result: TesterResult, path: Path | None = None) -> str:
    use = result.usage
    lines = [f"Tester of attempt {result.number} of {result.key} in run {result.run_id}"]
    if result.skipped:
        lines.append(f"Tester skipped: {result.skipped}")
    else:
        lines.append(
            f"Tester:    {result.limits.get('model')}, limit {result.limits.get('max_turns')} turns"
        )
        if use:
            cost = "unknown" if use.get("cost_usd") is None else f"${float(use['cost_usd']):.4f}"
            lines.append(f"Used:      {use.get('turns')} turns, {cost}, {use.get('seconds')}s")
    if result.summary:
        lines.append(f"Summary:   {result.summary}")
    lines += [f"  criterion {n}: {', '.join(tests)}" for n, tests in result.coverage.items()]
    lines += [f"  criterion {n} not tested: {why}" for n, why in result.uncovered.items()]
    if result.wrote:
        lines.append(f"Wrote ({len(result.wrote)}): {_names(result.wrote)}")
    flags = [
        ("NOT TESTS, written by the Tester", result.outside),
        ("Existing tests that lost a test or assertion", result.weakened),
        ("Named tests that cannot be used", result.invalid),
        ("Suspected defects", result.suspected_defects),
    ]
    lines += [f"{title}: {'; '.join(items)}" for title, items in flags if items]
    if result.unnamed:
        lines.append("No test and no reason for criteria: " + ", ".join(map(str, result.unnamed)))
    if result.no_tests:
        lines.append("The Tester named no tests.")
    for row in result.verify:
        mark = "ok    " if row["exit_code"] == 0 else "FAILED"
        how = "timed out" if row["timed_out"] else f"exit {row['exit_code']}"
        lines.append(f"  {mark} {row['command']}  ({how}, {row['seconds']:.1f}s)")
    if result.error:
        lines.append(f"Stopped: {result.error}")
    if path:
        lines.append(f"Report:    {path}")
    return "\n".join(lines)
