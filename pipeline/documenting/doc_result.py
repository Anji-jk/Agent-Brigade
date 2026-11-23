"""What one Documenter run did, as a record, as text and as ``docs/<KEY>-<n>.json``."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import run_directory, utc_now


@dataclass
class DocResult:
    run_id: str
    key: str
    number: int
    limits: dict[str, Any]
    wrote: list[str] = field(default_factory=list)  # files the Documenter wrote (measured)
    outside: list[str] = field(default_factory=list)  # of those, files the plan does not list
    report: str = ""  # the Documenter's own closing report
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    finished_at: str = field(default_factory=utc_now)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.outside


def write_doc_result(project_root: Path, result: DocResult) -> Path:
    path = (
        run_directory(project_root, result.run_id) / "docs" / f"{result.key}-{result.number}.json"
    )
    data = asdict(result)
    data["ok"] = result.ok
    write_json_atomic(path, data)
    return path


def format_doc_result(result: DocResult, path: Path | None = None) -> str:
    use = result.usage
    lines = [
        f"Documenter, attempt {result.number} of {result.key} in run {result.run_id}",
        f"Wrote ({len(result.wrote)}): {', '.join(result.wrote) or 'nothing'}",
    ]
    if result.outside:
        lines.append(f"Outside the task's Files, refused: {', '.join(result.outside)}")
    if use:
        lines.append(f"Used: {use.get('turns')} turns, ${use.get('cost_usd') or 0:.4f}")
    if result.error:
        lines.append(f"Error: {result.error}")
    elif result.report:
        lines += ["", result.report.strip()]
    if path:
        lines.append(f"Saved: {path}")
    return "\n".join(lines)
