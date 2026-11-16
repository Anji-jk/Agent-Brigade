"""The checks run on a merge that is not committed yet, and what they say about it.

After a real merge the combined code is checked before the story branch moves: the plan's project
checks and the task's own Verify lines, in the story worktree. A line that already failed at
baseline (eslint on a project whose lint is red) cannot tell whether the merge made things worse,
so it never blocks a merge, and it is named in the notes. Any other failing line blocks it.
"""

from pathlib import Path
from typing import Any

from pipeline.stages.baseline import Baseline
from pipeline.workspace.commands import CommandResult, run_command

TAIL_CHARS = 1500


def check_lines(plan: dict[str, Any], task: dict[str, Any]) -> list[str]:
    """The plan's project checks, then the task's Verify lines, each once."""
    lines: list[str] = []
    for line in [*plan["commands"].get("project_checks", []), *task.get("verification", [])]:
        if line not in lines:
            lines.append(line)
    return lines


def run_checks(
    lines: list[str], worktree: Path, baseline: dict[str, Baseline], timeout: int
) -> tuple[list[dict[str, Any]], list[CommandResult], list[str]]:
    """(one row per line, the lines that block the merge, notes about lines that cannot)."""
    rows: list[dict[str, Any]] = []
    blocking: list[CommandResult] = []
    notes: list[str] = []
    for line in lines:
        result = run_command(line, worktree, timeout=timeout)
        before = baseline.get(line)
        if result.passed:
            how = "ok"
        elif before is not None and before.failed:
            how = "FAILED (also at baseline, cannot judge the merge)"
            notes.append(
                f"`{line}` failed before any agent too, so it cannot tell if the merge hurt."
            )
        else:
            how = "FAILED (new)"
            blocking.append(result)
        rows.append({"line": line, "ok": result.passed, "how": how})
    return rows, blocking, notes


def failure_text(blocking: list[CommandResult]) -> list[str]:
    """One reason per blocking line, with the end of its output."""
    reasons = []
    for result in blocking:
        tail = result.output_tail.strip()[-TAIL_CHARS:] or "(no output)"
        why = "timed out" if result.timed_out else f"failed (exit {result.exit_code})"
        reasons.append(
            f"The check `{result.command}` {why} on the merged code. Its output ended:\n{tail}"
        )
    return reasons
