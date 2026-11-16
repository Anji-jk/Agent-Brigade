"""The story loop's log (story-events.jsonl): one JSON line per thing that happened.

It is how a person (and later the Orchestrator tab) sees what the loop did, in order, while it
runs or after it stopped. Lines are only ever appended. A last line torn by a crash is skipped
when reading, so the log never stops being readable.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.runs import run_directory

FILE = "story-events.jsonl"


def events_path(root: Path, run_id: str) -> Path:
    return run_directory(root, run_id) / FILE


def record(root: Path, run_id: str, kind: str, **data: Any) -> None:
    """Append one event: its kind, the time, and whatever `data` says (key, attempt, text...)."""
    path = events_path(root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"kind": kind, "at": datetime.now(UTC).isoformat(), **data})
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_events(root: Path, run_id: str) -> list[dict[str, Any]]:
    """Every event of the run, oldest first; [] when there are none."""
    path = events_path(root, run_id)
    if not path.is_file():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            found.append(json.loads(line))
        except ValueError:
            continue
    return found
