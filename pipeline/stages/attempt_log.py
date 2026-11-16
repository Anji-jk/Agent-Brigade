"""What happened in one attempt of one task, kept the way Agent Lab keeps a task's events.

Everything of attempt `n` of a task lives in ``<run folder>/attempts/<KEY>-<n>/``:

events.jsonl            the orchestrator's steps, one JSON line each: builder started, checks
                        finished, merge finished... (``AttemptLog.emit``)
<role>.events.jsonl     what one agent did, as Claude Code streamed it (the raw stream-json lines)
<role>.events.times     one UTC time per line of that file, because Claude's events carry none

The dashboard reads these folders. Writing them is best effort: a log that cannot be written
must never stop a task, so ``emit`` reports failure by returning False instead of raising.
Agent lines can contain whatever the agent printed, secrets included: whoever shows them masks
them first.
"""

import json
from pathlib import Path
from typing import Any

from core.runs import run_directory, utc_now

FILE = "events.jsonl"
FOLDER = "attempts"


def attempt_dir(root: Path, run_id: str, key: str, number: int) -> Path:
    return run_directory(root, run_id) / FOLDER / f"{key}-{number}"


def agent_events_path(root: Path, run_id: str, key: str, number: int, role: str) -> Path:
    """Where the stream of `role` (builder, tester, reviewer) is kept for this attempt."""
    return attempt_dir(root, run_id, key, number) / f"{role}.events.jsonl"


class AttemptLog:
    def __init__(self, root: Path, run_id: str, key: str, number: int):
        self.path = attempt_dir(root, run_id, key, number) / FILE

    def emit(self, step: str, **fields: Any) -> bool:
        """Append one step with its time and facts. False when it could not be written."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps({"at": utc_now(), "step": step, **fields}, default=str)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except (OSError, TypeError, ValueError):
            return False
        return True
