"""Finding a run of this project: its repository folder and its database row."""

from pathlib import Path

from sqlalchemy.orm import Session

from backend.services.planning_types import NotFound, PlanningServiceError
from core.db.models import StoryRun
from core.db.repositories import story_runs as runs
from core.db.repositories.projects import sync_env_project
from core.runs import RunIdError, validate_run_id
from core.settings import Settings
from pipeline.workspace.git import GitError, repository_root

_ROOTS: dict[Path, Path] = {}  # folder -> its repository's top folder, once found


def project_root(settings: Settings) -> Path:
    """The project's repository folder. Asking Git costs about a second on some Windows setups
    and every page read needs it, so a found answer is kept (a repository does not move while
    the server runs); a failure is never kept, so fixing .env and retrying works."""
    folder = settings.project_path
    if folder is None:
        raise PlanningServiceError("No project: BRIGADE_PROJECT_PATH is empty in .env.")
    if folder in _ROOTS:
        return _ROOTS[folder]
    try:
        _ROOTS[folder] = repository_root(folder)
    except GitError as exc:
        raise PlanningServiceError(str(exc)) from None
    return _ROOTS[folder]


def find_run(session: Session, settings: Settings, run_id: str) -> StoryRun:
    """The run's row, or NotFound: a run id that cannot be one is not found either."""
    project = sync_env_project(session, settings)
    try:
        validate_run_id(run_id)
    except RunIdError:
        raise NotFound(f"Run {run_id} was not found in this project.") from None
    row = runs.get_run(session, project.id, run_id) if project else None
    if row is None:
        raise NotFound(f"Run {run_id} was not found in this project.")
    return row
