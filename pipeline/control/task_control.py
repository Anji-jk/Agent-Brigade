"""Stop and Cancel of one task, kept as two small files in the run's ``control`` folder.

The story loop owns every agent it started, so it is the loop that stops them: the page only
leaves a note, and the loop reads it. Nothing here needs a process id, so nothing can ever kill
a process that is not ours.

``<KEY>.request``  "stop" or "cancel": a person asked, the loop has not acted on it yet. An agent
                   that is running notices it within a second and is stopped by its own loop.
``<KEY>.json``     what the loop (or, for a task that is not running, the page) settled:
                   state ``stopped`` (it can be continued) or ``cancelled`` (final), the stage
                   it will resume from, and the attempt it was on.
``<KEY>.agent``    the agent process the loop has running for the task, written when it starts and
                   removed when it ends (pipeline.runner.agent_record). If it is still there after
                   the loop died, that agent may be an orphan.

Both are plain files, so a restart of the server or of the loop loses nothing, and ``reset``
removes them with the rest of the run's folder.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from core.files.atomic import write_json_atomic
from core.runs import STORY_KEY_PATTERN, utc_now

FOLDER = "control"
STOP, CANCEL = "stop", "cancel"
STOPPED, CANCELLED = "stopped", "cancelled"


@dataclass(frozen=True)
class Settled:
    state: str  # stopped | cancelled
    stage: str | None  # builder | checks | tester | judge: where Continue resumes
    attempt: int | None
    at: str
    reason: str | None = None  # why it stopped, when the loop (not a person) stopped it


def _path(run_dir: Path, key: str, suffix: str) -> Path:
    if not isinstance(key, str) or not STORY_KEY_PATTERN.fullmatch(key):
        raise ValueError(f"Not a Jira key: {key!r}")
    return Path(run_dir) / FOLDER / f"{key}.{suffix}"


def request_path(run_dir: Path, key: str) -> Path:
    return _path(run_dir, key, "request")


def agent_record_path(run_dir: Path, key: str) -> Path:
    return _path(run_dir, key, "agent")


def unsettle(run_dir: Path, key: str) -> None:
    """Take back a Stop (Continue): the task is no longer stopped. Used only by Continue."""
    _path(run_dir, key, "json").unlink(missing_ok=True)


def ask(run_dir: Path, key: str, action: str, reason: str | None = None) -> None:
    """Leave the request. A Cancel is never weakened into a Stop by a later Stop.
    `reason` is the loop's own words when it, not a person, is the one stopping the task."""
    if action not in (STOP, CANCEL):
        raise ValueError(f"Not an action: {action!r}")
    if pending(run_dir, key) == CANCEL:
        return
    note = {"action": action, "at": utc_now()}
    if reason:
        note["reason"] = reason
    write_json_atomic(request_path(run_dir, key), note)


def pending(run_dir: Path, key: str) -> str | None:
    """The waiting request: stop, cancel, or None. A damaged note counts as a Stop, the safe one."""
    path = request_path(run_dir, key)
    if not path.exists():
        return None
    try:
        action = json.loads(path.read_text(encoding="utf-8")).get("action")
    except (OSError, ValueError, AttributeError):
        return STOP
    return CANCEL if action == CANCEL else STOP


def reason_of(run_dir: Path, key: str) -> str | None:
    """The reason written with the waiting request, or None (a person's own Stop has none)."""
    try:
        data = json.loads(request_path(run_dir, key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    reason = data.get("reason") if isinstance(data, dict) else None
    return reason if isinstance(reason, str) and reason else None


def clear_request(run_dir: Path, key: str) -> None:
    request_path(run_dir, key).unlink(missing_ok=True)


def settle(
    run_dir: Path, key: str, state: str, stage: str | None, attempt: int | None,
    reason: str | None = None,
) -> None:  # fmt: skip
    """Record the final word on the task (the request is spent) and drop the request."""
    if state not in (STOPPED, CANCELLED):
        raise ValueError(f"Not a state: {state!r}")
    record = {"state": state, "stage": stage, "attempt": attempt, "at": utc_now()}
    if reason:
        record["reason"] = reason
    write_json_atomic(_path(run_dir, key, "json"), record)
    clear_request(run_dir, key)


def settled(run_dir: Path, key: str) -> Settled | None:
    path = _path(run_dir, key, "json")  # a key that is not a Jira key is refused here, loudly
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("state") not in (STOPPED, CANCELLED):
        return None
    attempt = data.get("attempt")
    return Settled(
        data["state"],
        data.get("stage") if isinstance(data.get("stage"), str) else None,
        attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else None,
        str(data.get("at") or ""),
        data.get("reason") if isinstance(data.get("reason"), str) else None,
    )
