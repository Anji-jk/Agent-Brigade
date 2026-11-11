"""Use cases for projects."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models import Project
from core.settings import Settings


def sync_env_project(session: Session, settings: Settings) -> Project | None:
    """Save the project named in .env as a row in `projects`; update it if it already exists.

    Returns None when .env names no project folder yet (local_path is required by the schema).
    """
    name = settings.resolved_project_name
    if not name or settings.project_path is None:
        return None
    project = session.scalars(select(Project).where(Project.name == name)).first()
    if project is None:
        project = Project(name=name, local_path="", base_branch="")
        session.add(project)
    project.repository = settings.repository or None
    project.local_path = str(settings.project_path)
    project.base_branch = settings.base_branch
    session.flush()
    return project


def list_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.name)))
