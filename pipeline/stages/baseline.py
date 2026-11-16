"""How the project's own checks ended before any agent touched it, read from prepare's report.

``prepare`` runs the plan's project checks once on the untouched story branch and writes the
results to ``build/prepare.json``. A Verify line that failed then (eslint on a project whose lint
is red) says nothing new when it fails again; one that passed then, and fails now, is a defect.
Lines are matched by their exact text: a task's line that differs from every baseline line is a
check the project did not run before, and counts as new.
"""

from dataclasses import dataclass
from pathlib import Path

from core.runs import run_directory
from pipeline.stages.stage_inputs import read_report


@dataclass(frozen=True)
class Baseline:
    failed: bool
    output_tail: str


def read_baseline(root: Path, run_id: str) -> dict[str, Baseline]:
    """Each baseline line's result by its text. Empty when prepare's report is missing."""
    data = read_report(run_directory(root, run_id) / "build" / "prepare.json")
    found: dict[str, Baseline] = {}
    for step in (data or {}).get("baseline", []):
        if isinstance(step, dict) and isinstance(step.get("line"), str):
            found[step["line"]] = Baseline(
                step.get("status") == "failed", str(step.get("output_tail") or "")
            )
    return found
