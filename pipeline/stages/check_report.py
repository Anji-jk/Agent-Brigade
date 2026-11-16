"""What the checks of one attempt found: database rows, text and ``checks/<KEY>-<n>.json``."""

from dataclasses import asdict
from pathlib import Path

from core.files.atomic import write_json_atomic
from core.runs import run_directory, utc_now
from pipeline.checks.measure import CheckReport

SHOWN_FILES = 30


def _names(paths: list[str]) -> str:
    shown = ", ".join(paths[:SHOWN_FILES])
    return shown + (f" ... and {len(paths) - SHOWN_FILES} more" if len(paths) > SHOWN_FILES else "")


def check_rows(report: CheckReport) -> list[tuple[str, bool, str]]:
    """The rows of the checks table: (kind, passed, text). One verify row per line that ran."""
    rows = [
        ("changes", bool(report.changed), _names(report.changed) or "no file changed"),
        ("protected", not report.protected, _names(report.protected) or "none touched"),
        (
            "scope",
            not report.extra,
            ("outside the task's Files: " + _names(report.extra)) if report.extra
            else "every changed file is in the task's Files",
        ),
    ]  # fmt: skip
    for result in report.verify:
        status = "timed out" if result.timed_out else f"exit {result.exit_code}"
        text = f"$ {result.command}\n{status}, {result.seconds:.1f}s\n{result.output_tail}"
        rows.append(("verify", result.passed, text))
    return rows


def write_check_report(project_root: Path, run_id: str, report: CheckReport) -> Path:
    path = run_directory(project_root, run_id) / "checks" / f"{report.key}-{report.number}.json"
    data = asdict(report)
    data.update(passed=report.passed, failures=report.failures(), finished_at=utc_now())
    write_json_atomic(path, data)
    return path


def format_checks(report: CheckReport, run_id: str, path: Path | None = None) -> str:
    lines = [f"Checks of attempt {report.number} of {report.key} in run {run_id}"]
    lines.append(f"Changed ({len(report.changed)}): {_names(report.changed) or 'nothing'}")
    if report.extra:
        lines.append(f"Outside the task's Files ({len(report.extra)}), for the Reviewer: "
                     f"{_names(report.extra)}")  # fmt: skip
    if report.protected:
        lines.append(f"PROTECTED, must not change: {_names(report.protected)}")
        lines.append("Verify lines: not run, because a protected path changed.")
    elif not report.verify_lines:
        lines.append("Verify lines: the task lists none, so no result was measured.")
    for result in report.verify:
        mark = "ok    " if result.passed else "FAILED"
        how = "timed out" if result.timed_out else f"exit {result.exit_code}"
        lines.append(f"  {mark} {result.command}  ({how}, {result.seconds:.1f}s)")
        if not result.passed and result.output_tail.strip():
            lines += [f"      {x}" for x in result.output_tail.strip().splitlines()[-8:]]
    if report.failed_verify():
        lines.append(f"Verify failed ({len(report.failed_verify())}): the Reviewer judges this.")
    lines.append("No blocking check failed." if report.passed else "Failed:")
    lines += [f"  {text}" for text in report.failures()]
    if path:
        lines.append(f"Report:    {path}")
    return "\n".join(lines)
