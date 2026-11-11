from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import backend.services.projects as service
from backend.schemas.project import ProjectOut
from core.db import get_session

router = APIRouter()


def db_session(request: Request) -> Iterator[Session]:
    with get_session(request.app.state.engine) as session:
        yield session


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: Annotated[Session, Depends(db_session)]) -> list[ProjectOut]:
    return [ProjectOut.model_validate(p) for p in service.list_projects(session)]
