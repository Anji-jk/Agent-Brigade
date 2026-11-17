"""A note of the agent process a loop has running, so that a dead loop's agent can be found.

The loop that starts an agent is the one that stops it. If the loop itself dies (a crash, a
power cut, a killed terminal) its agent may keep running in the task's worktree. While an agent
runs, ``recorded`` keeps a small file with its process id and its session id; the file goes when
the agent ends, however it ends. Continue reads what is left behind (pipeline.control.
interrupted) and stops the agent before it starts another one in the same worktree.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.files.atomic import write_json_atomic
from core.runs import utc_now


@dataclass(frozen=True)
class AgentRecord:
    pid: int
    session_id: str
    started_at: str


@contextmanager
def recorded(path: Path | None, pid: int, session_id: str) -> Iterator[None]:
    """Keep the note while the block runs. With no `path`, nothing is written. Best effort:
    a note that cannot be written never stops the agent."""
    if path is not None:
        try:
            write_json_atomic(path, {"pid": pid, "session_id": session_id, "started_at": utc_now()})
        except OSError:
            path = None
    try:
        yield
    finally:
        if path is not None:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass


def read_record(path: Path) -> AgentRecord | None:
    """The note, or None when there is none or it is damaged."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        pid = data["pid"]
        session = data["session_id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(pid, int) or isinstance(pid, bool) or not isinstance(session, str):
        return None
    return AgentRecord(pid, session, str(data.get("started_at") or ""))
