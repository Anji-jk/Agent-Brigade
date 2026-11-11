from fastapi import APIRouter, Request

from backend.schemas.project import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    settings = request.app.state.settings
    return HealthOut(
        status="ok",
        project=settings.resolved_project_name or None,
        jira_site_url=settings.jira_site_url,
        jira_configured=settings.jira_configured,
        user_initials=settings.user_initials,
    )
