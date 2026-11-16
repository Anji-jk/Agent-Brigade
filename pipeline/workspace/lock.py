"""Lock files: one merge at a time into the story branch, one story loop at a time per run.

Merges change the story branch, so two of them must never run together. The lock is a file made
with O_EXCL, which only one process can win. It is removed when the holder ends, however it ends.
A lock left by a crash is not removed on its own: the message names the file and the process id
that made it, and a person deletes it once that process is gone.
"""

import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path


class LockError(RuntimeError):
    """The lock is held by another process. The message says by whom and what to do."""


@contextmanager
def file_lock(path: Path, held_by: str) -> Iterator[None]:
    """Hold the lock file `path`; `held_by` completes "<held_by> (process N)" in the refusal."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            holder = path.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            holder = "unknown"
        raise LockError(
            f"{held_by} (process {holder}). If that process is gone, delete {path} and try again."
        ) from None
    try:
        os.write(handle, str(os.getpid()).encode())
    finally:
        os.close(handle)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def merge_lock(folder: Path) -> AbstractContextManager[None]:
    """One merge at a time into the story branch."""
    return file_lock(Path(folder) / "merge.lock", "Another merge holds the lock")


def run_lock(folder: Path) -> AbstractContextManager[None]:
    """One story loop at a time per run: two loops would start the same task twice."""
    return file_lock(Path(folder) / "story.lock", "A story loop is already running")
