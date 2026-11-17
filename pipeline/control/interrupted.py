"""Finding the tasks a dead loop left in the middle, and the agent it may have left running.

A loop that dies (a crash, a power cut, a closed terminal) cannot record that it died. What is
left says it: a task's attempt that is not finished, while no process of ours is running the
loop. A read of the run (the progress page, or Continue itself) calls ``notice``, which turns
each such task into a *stopped* one at its last checkpoint, exactly as if a person had stopped
it, so the same Continue goes on from it.

The check is always the recorded command line, never a process id alone: a process id is handed
to another program once its process ends, and killing that would be killing a stranger.
"""

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories import merge_rows
from core.runs import run_directory
from pipeline.control import state as states
from pipeline.control import task_control as control
from pipeline.control.launch import LOCK_FILE, is_loop_process
from pipeline.control.processes import CommandLine, command_line
from pipeline.runner.agent_record import read_record
from pipeline.stages.attempt_log import AttemptLog
from pipeline.stages.interrupt import settle_waiting
from pipeline.workspace.commands import kill_tree

UNFINISHED = (None, "built")  # an attempt the judge has not decided


def reap_orphan(
    run_dir: Path,
    key: str,
    lines: CommandLine = command_line,
    kill: Callable[[Any], None] = kill_tree,
) -> bool:
    """Stop the agent a dead loop left for `key`, if it is still the agent we started.

    True: an agent was found running and stopped. Its session id must be in the command line of
    the process now holding the recorded id, or nothing is touched."""
    path = control.agent_record_path(run_dir, key)
    record = read_record(path)
    if record is None:
        return False
    line = lines(record.pid)
    ours = bool(line) and record.session_id in line
    if ours:
        kill(SimpleNamespace(pid=record.pid))
    path.unlink(missing_ok=True)
    return ours


def clear_stale_lock(run_dir: Path, run_id: str, lines: CommandLine = command_line) -> bool:
    """Remove ``story.lock`` when the loop that made it is gone. True: a stale lock was removed.

    A loop killed from outside cannot remove its own lock, and the next loop would refuse to
    start for ever. The lock is stale only if the process named in it is no longer this run's
    loop (the command line is checked, never the process id alone: ids are handed out again)."""
    path = Path(run_dir) / LOCK_FILE
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = None
    if pid is not None and is_loop_process(lines(pid), run_id):
        return False
    try:
        path.unlink()
    except OSError:  # no lock, or it cannot be removed: starting will say so
        return False
    return True


def unfinished_keys(engine: Engine, run_id: str) -> list[str]:
    """The tasks whose newest attempt has not been judged, in the order they were started."""
    with get_session(engine) as session:
        facts = merge_rows.attempts_of_run(session, run_id)
    newest = {fact.key: fact for fact in facts}  # oldest first: the last of a task wins
    return [key for key, fact in newest.items() if fact.outcome in UNFINISHED]


def _log(engine: Engine, root: Path, run_id: str, key: str, state: str, stage: str) -> None:
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, run_id, key)
    if found is not None:
        AttemptLog(root, run_id, key, found[1].number).emit(
            "task_interrupted", state=state, stage=stage,
            why="the loop that was working on it is gone",
        )  # fmt: skip


def notice(
    engine: Engine,
    root: Path,
    run_id: str,
    lines: CommandLine = command_line,
    kill: Callable[[Any], None] = kill_tree,
    quick: bool = False,
) -> list[str]:
    """Mark the tasks an interrupted run left half-done as stopped. Returns their keys.

    Does nothing while a loop of the run is running, and nothing for a run that never started."""
    run_dir = run_directory(root, run_id)
    if states.build_state(run_dir, run_id, lines, quick) != states.INTERRUPTED:
        return []
    found = []
    for key in unfinished_keys(engine, run_id):
        settled = control.settled(run_dir, key)
        if settled and settled.state == control.CANCELLED:
            continue
        reap_orphan(run_dir, key, lines, kill)
        action = control.pending(run_dir, key) or control.STOP
        state, stage = settle_waiting(engine, root, run_id, key, action)
        _log(engine, root, run_id, key, state, stage)
        found.append(key)
    return found
