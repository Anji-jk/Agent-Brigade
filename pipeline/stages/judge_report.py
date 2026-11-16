"""What judging an attempt decided: a record, as text and as ``judge/<KEY>-<n>.json``."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import utc_now
from pipeline.checks.decide import DONE, FAILED
from pipeline.stages.stage_inputs import report_path

WORDS = {DONE: "Done", FAILED: "Failed", "needs_review": "Needs review"}


@dataclass
class JudgeResult:
    run_id: str
    key: str
    number: int
    outcome: str = ""
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    feedback: str = ""  # what the next Builder is told, when the outcome is failed
    commit: str | None = None
    left_over: list[str] = field(default_factory=list)  # changed files that were not committed
    reviewer_skipped: str | None = None
    verdict: str | None = None
    criteria: list[dict[str, Any]] = field(default_factory=list)  # criterion, text, met, evidence
    problems: list[str] = field(default_factory=list)  # the Reviewer's
    verify: list[dict[str, Any]] = field(default_factory=list)  # line, passed, how it is judged
    limits: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    finished_at: str = field(default_factory=utc_now)

    @property
    def done(self) -> bool:
        return self.outcome == DONE


def write_judge_report(root: Path, result: JudgeResult) -> Path:
    path = report_path(root, result.run_id, "judge", result.key, result.number)
    data = asdict(result)
    data["done"] = result.done
    write_json_atomic(path, data)
    return path


def _reviewer_lines(result: JudgeResult) -> list[str]:
    if result.reviewer_skipped:
        return [f"Reviewer skipped: {result.reviewer_skipped}"]
    use, cap = result.usage, result.limits
    cost = "unknown" if use.get("cost_usd") is None else f"${float(use['cost_usd']):.4f}"
    lines = [
        f"Reviewer:  {cap.get('model')}, limit {cap.get('max_turns')} turns",
        f"Used:      {use.get('turns')} turns, {cost}, {use.get('seconds')}s",
    ]
    if result.verdict:
        lines.append(f"Verdict:   {result.verdict}")
    for row in result.criteria:
        mark = "met    " if row["met"] else "NOT MET"
        lines.append(f"  {mark} {row['criterion']}. {row['text']}")
        lines.append(f"          {row['evidence']}")
    lines += [f"  problem: {text}" for text in result.problems]
    return lines


def format_judge(result: JudgeResult, path: Path | None = None) -> str:
    lines = [f"Decision for attempt {result.number} of {result.key} in run {result.run_id}"]
    for row in result.verify:
        lines.append(f"  check {row['how']}: {row['line']}")
    lines += _reviewer_lines(result)
    lines += [f"Note: {text}" for text in result.notes]
    lines.append(f"{WORDS.get(result.outcome, result.outcome).upper()}")
    lines += [f"  - {text}" for text in result.reasons]
    if result.feedback:
        lines += [
            "Feedback for the next Builder:",
            *[f"  | {x}" for x in result.feedback.split("\n")],
        ]
    if result.commit:
        lines.append(f"Committed: {result.commit[:12]} in the attempt worktree (not merged yet)")
    elif result.outcome == DONE:
        lines.append("Committed: nothing")
    else:
        lines.append("Nothing was committed. The worktree stays for you to look at.")
    if result.left_over:
        lines.append("Left behind, not committed: " + ", ".join(result.left_over[:20]))
    if path:
        lines.append(f"Report:    {path}")
    return "\n".join(lines)
