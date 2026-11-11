"""The FastAPI app. Start it from the repo folder:

uvicorn backend.main:create_app --factory --port 8000
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.api import health, projects
from backend.services.projects import sync_env_project
from core.db import get_session, init_db, make_engine
from core.settings import Settings, get_settings

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        settings.ensure_dirs()
        engine = init_db(make_engine(settings.db_path))
        with get_session(engine) as session:
            sync_env_project(session, settings)
        app.state.engine = engine
        yield
        engine.dispose()

    app = FastAPI(title="Agent Brigade", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    # Last, so /api/* wins: the page and its files
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app
