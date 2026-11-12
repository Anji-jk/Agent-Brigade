"""The FastAPI app. Start it from the repo folder:

uvicorn backend.main:create_app --factory --port 8000
"""

import mimetypes
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.api import health, planning, projects, publisher
from backend.services.planning import Executor, PlanningService
from backend.services.projects import sync_env_project
from backend.services.publisher import PublisherService
from core.db import get_session, init_db, make_engine
from core.settings import Settings, get_settings
from core.trackers.jira.client import JiraClient
from pipeline.publisher.transcript import CLAUDE_HOME
from pipeline.runner.claude_runner import AgentRunner, ClaudeCliRunner

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
# Windows can map .js to text/plain in its registry; browsers then refuse the page's scripts.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


def load_settings() -> Settings:
    """Settings, or a one-line-per-problem message naming each bad variable instead of a trace."""
    try:
        return get_settings()
    except ValidationError as error:
        lines = [
            f"  {'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        ]
        raise SystemExit(
            "Brigade cannot start. Fix these settings in .env:\n" + "\n".join(lines)
        ) from None


def create_app(
    settings: Settings | None = None,
    *,
    runner: AgentRunner | None = None,
    jira_factory: Callable[[Settings], JiraClient] = JiraClient.from_settings,
    claude_home: Path = CLAUDE_HOME,
    planning_executor: Executor | None = None,
) -> FastAPI:
    """The app. Tests pass a fake runner, a fake Jira, a temporary Claude folder and an executor
    that plans at once instead of in a worker thread."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        settings.ensure_dirs()
        engine = init_db(make_engine(settings.db_path))
        with get_session(engine) as session:
            sync_env_project(session, settings)
        app.state.engine = engine
        agents = runner or ClaudeCliRunner()
        app.state.publisher = PublisherService(settings, engine, agents, jira_factory, claude_home)
        app.state.planning = PlanningService(
            settings, engine, agents, jira_factory, planning_executor
        )
        app.state.planning.recover()  # runs left planning by the last stop are marked failed
        yield
        app.state.planning.close()
        engine.dispose()

    app = FastAPI(title="Agent Brigade", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(publisher.router, prefix="/api")
    app.include_router(planning.router, prefix="/api")
    # Last, so /api/* wins: the page and its files
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app
