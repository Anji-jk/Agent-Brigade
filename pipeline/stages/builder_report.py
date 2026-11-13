"""What one Builder attempt did, as a record, as text and as ``build/<KEY>-<n>.json``."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import run_directory, utc_now
from pipeline.stages.prepare_report import StepResult, step_lines


@dataclass
class BuildResult:
    run_id: str
    key: str
    number: int
    branch: str
    worktree: str
    limits: dict[str, Any]  # model, effort, max_turns, max_budget_usd
    setup: list[StepResult] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)  # files the worktree differs in
    usage: dict[str, Any] = field(default_factory=dict)  # cost, turns, tokens, seconds, session
    report: str = ""  # the Builder's own closing report
    error: str | None = None  # why there is no usable answer (setup, agent, project folder)
    finished_at: str = field(default_factory=utc_now)

    @property
    def ok(self) -> bool:
        return self.error is None


def write_build_report(project_root: Path, result: BuildResult) -> Path:
    path = (
        run_directory(project_root, result.run_id) / "build" / f"{result.key}-{result.number}.json"
    )
    data = asdict(result)
    data["ok"] = result.ok
    write_json_atomic(path, data)
    return path


def _money(value: float | None) -> str:
    return "unknown" if value is None else f"${float(value):.4f}"


def format_build(result: BuildResult, report: Path | None = None) -> str:
    use, cap = result.usage, result.limits
    lines = [
        f"Attempt {result.number} of {result.key} in run {result.run_id}",
        f"Branch:    {result.branch}",
        f"Worktree:  {result.worktree}",
        *step_lines("Setup:", result.setup),
        f"Builder:   {cap.get('model')}, {cap.get('effort')} effort, "
        f"limit {cap.get('max_turns')} turns and {_money(cap.get('max_budget_usd'))}",
    ]
    if use:
        lines.append(
            f"Used:      {use.get('turns')} turns, {_money(use.get('cost_usd'))}, "
            f"{use.get('seconds')}s, tokens in/out/cache "
            f"{use.get('input_tokens')}/{use.get('output_tokens')}/{use.get('cache_tokens')}"
        )
        lines.append(f"Session:   {use.get('session_id')}")
    if result.changed:
        lines.append(f"Changed ({len(result.changed)}), not committed:")
        lines += [f"  {name}" for name in result.changed[:30]]
        if len(result.changed) > 30:
            lines.append(f"  ... and {len(result.changed) - 30} more")
    elif result.ok:
        lines.append("Changed:   nothing (the worktree is the same as the story branch)")
    if result.report:
        lines += ["Builder's report:", *[f"  {x}" for x in result.report.strip().splitlines()]]
    lines.append(
        "Built. Look at the worktree, then run clean when done."
        if result.ok
        else f"Stopped: {result.error}"
    )
    if report:
        lines.append(f"Report:    {report}")
    return "\n".join(lines)
