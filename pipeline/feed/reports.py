"""What an agent did, as the page shows it: a stage's report, with only the fields it needs.

Each stage writes ``build/``, ``test/`` or ``judge/<KEY>-<n>.json`` (pipeline.stages). The page
gets the part a person reads after the agent finishes: what changed, what it said, what it cost.
Fields are chosen by name, so a field added to a report later is not shown by accident. Every
text is masked for secrets and shortened, as the event feeds are.
"""

from pathlib import Path
from typing import Any

from core.masking import mask_secrets
from pipeline.feed.items import shorten
from pipeline.feed.sources import KEY, FeedError
from pipeline.stages.stage_inputs import read_report, report_path

SHARED = ("usage", "limits", "finished_at")
FIELDS = {
    "build": ("ok", "error", "changed", "report", *SHARED),
    "test": (
        "ran",
        "skipped",
        "error",
        "summary",
        "coverage",
        "uncovered",
        "suspected_defects",
        "notes",
        "wrote",
        "outside",
        "weakened",
        "invalid",
        "no_tests",
        *SHARED,
    ),  # fmt: skip
    "judge": (
        "outcome",
        "reasons",
        "notes",
        "commit",
        "verdict",
        "criteria",
        "problems",
        "reviewer_skipped",
        *SHARED,
    ),  # fmt: skip
}  # the Builder's, the Tester's and the Reviewer's (the judge's) own words and measures
HIDDEN = ("session_id",)  # inside usage: nothing the page needs


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return shorten(mask_secrets(value))[0]
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items() if k not in HIDDEN}
    return value


def stage_report(root: Path, run_id: str, key: str, number: int, stage: str) -> dict[str, Any]:
    """The stage's report for the page. `exists` is False while the stage has not written it.
    FeedError: the stage, key or number cannot be one."""
    if stage not in FIELDS:
        raise FeedError(f"Not a stage: {stage!r}. Use one of {', '.join(FIELDS)}.")
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise FeedError(f"Not a task key: {key!r}")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise FeedError(f"Not an attempt number: {number!r}")
    found = read_report(report_path(root, run_id, stage, key, number))
    if found is None:
        return {"stage": stage, "exists": False}
    return {
        "stage": stage,
        "exists": True,
        **{n: _clean(found[n]) for n in FIELDS[stage] if n in found},
    }
