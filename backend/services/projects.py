"""Use cases for projects. The queries live in core.db.repositories, for the pipeline too."""

from core.db.repositories.projects import list_projects, sync_env_project

__all__ = ["list_projects", "sync_env_project"]
