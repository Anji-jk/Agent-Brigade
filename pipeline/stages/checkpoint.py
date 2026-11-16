"""Which stages of an attempt are done, so that Continue does not pay for them again.

``attempts/<KEY>-<n>/checkpoint.json`` lists the stages that finished well, in order: builder,
checks, tester. It is written the moment each one ends, so a stop (or a crash) at any time
leaves the last finished stage on record. What each stage found is already in its own report
(build, checks, test); this file only says which of them can be trusted as complete.
"""

import json
from pathlib import Path

from core.files.atomic import write_json_atomic
from core.runs import utc_now
from pipeline.stages.attempt_log import attempt_dir

FILE = "checkpoint.json"
ORDER = ("builder", "checks", "tester", "judge")  # judge: what is left, never saved as done


def _path(root: Path, run_id: str, key: str, number: int) -> Path:
    return attempt_dir(root, run_id, key, number) / FILE


def completed(root: Path, run_id: str, key: str, number: int) -> list[str]:
    """The stages that finished well, in order; empty when there is no readable record."""
    try:
        data = json.loads(_path(root, run_id, key, number).read_text(encoding="utf-8"))
        stages = data["completed"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [name for name in ORDER if isinstance(stages, list) and name in stages]


def save(root: Path, run_id: str, key: str, number: int, stage: str) -> None:
    """Add `stage` to the finished ones. Best effort: an unwritable note stops nothing."""
    if stage not in ORDER:
        raise ValueError(f"Not a stage: {stage!r}")
    done = completed(root, run_id, key, number)
    if stage in done:
        return
    names = [name for name in ORDER if name in (*done, stage)]
    try:
        write_json_atomic(_path(root, run_id, key, number), {"completed": names, "at": utc_now()})
    except OSError:
        return


def resume_stage(root: Path, run_id: str, key: str, number: int) -> str:
    """The first stage not yet finished: where Continue picks the attempt up."""
    done = completed(root, run_id, key, number)
    return next((name for name in ORDER if name not in done), ORDER[-1])