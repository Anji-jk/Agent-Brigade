"""Run ids and the folder a run keeps in the target project.

Every plan has a run id made from the story key, the UTC date and 4 hex characters, such as
``SMT-56-20261112-a3f9``. The plan that is approved is the story's run: its build, branch,
worktrees and logs use the same id. Older ids such as ``run-20261112-073015-a1b2c3`` stay valid.
Its files live in the target project at ``.agent-brigade/runs/<run_id>/``. That folder holds a
``.gitignore`` of ``*`` so Git ignores it: the project's ``git status`` stays clean and the
readiness check keeps passing after the first plan.

This is a folder inside the target project, not the platform's data folder (BRIGADE_DATA_DIR).
"""

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

PROJECT_FOLDER = ".agent-brigade"
RUNS_FOLDER = "runs"
RUN_ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}")
STORY_KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,9}-[1-9][0-9]{0,9}")
MAX_TRIES = 20  # 4 hex characters give 65,536 ids per story and day


class RunIdError(ValueError):
    """A run id that could not be a folder name of ours."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_run_id(
    story_key: str,
    taken: Callable[[str], bool] = lambda _run_id: False,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    """A new run id ``<story key>-<UTC date>-<4 hex characters>``, such as SMT-56-20261112-a3f9.

    `taken` says whether an id is already used (a run folder or a database row has it); a used
    id is made again, so two runs of a story on the same day never share one.
    """
    if not isinstance(story_key, str) or not STORY_KEY_PATTERN.fullmatch(story_key):
        raise RunIdError(f"Not a story key: {story_key!r}")
    stamp = now().strftime("%Y%m%d")
    for _ in range(MAX_TRIES):
        run_id = f"{story_key}-{stamp}-{secrets.token_hex(2)}"
        if not taken(run_id):
            return run_id
    raise RunIdError(f"No free run id for {story_key} today after {MAX_TRIES} tries.")


def validate_run_id(run_id: object) -> str:
    """The run id unchanged, or RunIdError: it becomes a folder name, so nothing else passes."""
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise RunIdError(f"Not a run id: {run_id!r}")
    return run_id


def project_folder(project_root: Path) -> Path:
    """``<project>/.agent-brigade``, created with its ``.gitignore`` the first time."""
    folder = Path(project_root) / PROJECT_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return folder


def run_directory(project_root: Path, run_id: str) -> Path:
    """``<project>/.agent-brigade/runs/<run_id>``. Only the path: nothing is created."""
    return Path(project_root) / PROJECT_FOLDER / RUNS_FOLDER / validate_run_id(run_id)
