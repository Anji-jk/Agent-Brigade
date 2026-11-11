from pydantic import BaseModel, ConfigDict


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    repository: str | None
    local_path: str
    base_branch: str


class HealthOut(BaseModel):
    status: str
    project: str | None  # name of the project Brigade works on, from .env
    jira_site_url: str
    jira_configured: bool
    user_initials: str
