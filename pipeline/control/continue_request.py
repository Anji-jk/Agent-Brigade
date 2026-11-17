"""Continue, as a note the loop reads: "go on with this task from where it stopped".

The page does not start agents. Continue takes the Stop back (``unsettle``) and leaves
``control/<KEY>.continue`` naming the attempt to go on with. A loop that is running picks the
note up on its next pass; when no loop is running, a new one is started and picks it up the same
way. A note that is left behind is harmless: it only means "continue this attempt", and it is
removed by the loop at the moment the task starts again.

An attempt is never copied: the work is in its worktree and on its branch, its reports are keyed
by its number, so the task goes on in the same attempt.
"""

import json
from pathlib import Path

from core.files.atomic import write_json_atomic
from core.runs import STORY_KEY_PATTERN, utc_now
from pipeline.control import task_control as control


def _path(run_dir: Path, key: str) -> Path:
    if not isinstance(key, str) or not STORY_KEY_PATTERN.fullmatch(key):
        raise ValueError(f"Not a Jira key: {key!r}")
    return Path(run_dir) / control.FOLDER / f"{key}.continue"


def release(run_dir: Path, key: str, attempt: int | None) -> None:
    """A person said Continue: the Stop is taken back and the attempt to go on with is noted.
    With no attempt (it was stopped before one began) the task simply starts as a new one."""
    control.unsettle(run_dir, key)
    if attempt is None:
        _path(run_dir, key).unlink(missing_ok=True)
        return
    write_json_atomic(_path(run_dir, key), {"attempt": attempt, "at": utc_now()})


def wanted(run_dir: Path, key: str) -> int | None:
    """The attempt a person asked to continue, or None when there is no (readable) note."""
    try:
        data = json.loads(_path(run_dir, key).read_text(encoding="utf-8"))
        number = data["attempt"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return number if isinstance(number, int) and not isinstance(number, bool) else None


def spent(run_dir: Path, key: str) -> None:
    _path(run_dir, key).unlink(missing_ok=True)
