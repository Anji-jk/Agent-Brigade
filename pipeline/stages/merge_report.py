"""What merging an attempt did: a record, as text and as ``merge/<KEY>-<n>.json``."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import utc_now
from pipeline.stages.stage_inputs import report_path

MERGED, FAILED = "merged", "failed"


@dataclass
class MergeResult:
    run_id: str
    key: str
    number: int
    branch: str  # the story branch
    attempt_commit: str
    outcome: str = ""
    kind: str = ""  # fast-forward | real
    tip_before: str = ""
    tip_after: str = ""  # the story tip now
    checks: list[dict[str, Any]] = field(default_factory=list)  # line, ok, how
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    feedback: str = ""  # what the next Builder is told when the merge failed
    finished_at: str = field(default_factory=utc_now)

    @property
    def merged(self) -> bool:
        return self.outcome == MERGED


def write_merge_report(root: Path, result: MergeResult) -> Path:
    path = report_path(root, result.run_id, "merge", result.key, result.number)
    data = asdict(result)
    data["merged"] = result.merged
    write_json_atomic(path, data)
    return path


def format_merge(result: MergeResult, path: Path | None = None) -> str:
    lines = [
        f"Merge of attempt {result.number} of {result.key} into {result.branch}",
        f"Story tip before: {result.tip_before[:12]}",
    ]
    if result.kind == "fast-forward":
        lines.append("Fast-forward: the story tip had not moved since the attempt started.")
    elif result.kind:
        lines.append("Real merge: the story tip moved, so the combined code was checked first.")
    lines += [f"  {row['how']}: {row['line']}" for row in result.checks]
    lines += [f"Note: {text}" for text in result.notes]
    if result.merged:
        lines.append(f"MERGED: the story tip is now {result.tip_after[:12]}")
    else:
        lines.append("FAILED: nothing was merged, the story branch is as it was.")
        lines += [f"  - {text}" for text in result.reasons]
        lines += [
            "Feedback for the next Builder:",
            *[f"  | {x}" for x in result.feedback.split("\n")],
        ]
    if path:
        lines.append(f"Report:    {path}")
    return "\n".join(lines)
