"""Publisher endpoints. Plain `def` handlers: FastAPI runs them in worker threads, so an agent turn
(often 20 to 60 seconds) never blocks other requests.

Messages are sent as a form (multipart), so files can come with them: a `text` field and any
number of `files` (at most 5, each .txt, .md, .docx or .pdf up to 10 MB).
"""

import json
from collections.abc import Callable
from typing import Annotated, TypeVar

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from backend.schemas.publisher import (
    BubbleOut,
    ChatOut,
    ChatSummaryOut,
    ConfirmOut,
    CreatedOut,
    FileOut,
    RecordOut,
    TurnOut,
)
from backend.services.publisher import (
    PublisherError,
    PublisherService,
    TurnResult,
    Upload,
    display_id,
)
from core.files.extract import MAX_BYTES
from core.trackers.errors import TrackerError
from pipeline.publisher.chat import ChatError
from pipeline.runner.claude_runner import AgentError

router = APIRouter(prefix="/publisher")
T = TypeVar("T")


def service(request: Request) -> PublisherService:
    return request.app.state.publisher


def run(action: Callable[[], T]) -> T:
    """The service call, with its errors turned into HTTP answers the page can show."""
    try:
        return action()
    except PublisherError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except ChatError as exc:
        raise HTTPException(400, str(exc)) from None
    except AgentError as exc:
        raise HTTPException(502, str(exc)) from None
    except TrackerError as exc:
        raise HTTPException(502, str(exc)) from None


def turn_out(result: TurnResult) -> TurnOut:
    turn = result.turn
    return TurnOut(
        chat_id=result.chat_id,
        display_id=display_id(result.chat_id),
        reply=turn.reply,
        plan=turn.plan.as_dict() if turn.plan else None,
        counts=turn.plan.counts() if turn.plan else None,
        problems=list(turn.problems),
        proposal_id=result.proposal_id,
        cost_usd=turn.cost_usd,
    )


def _plan(raw: str | None) -> dict | None:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


Text = Annotated[str, Form()]
Files = Annotated[list[UploadFile], File()]


def read_uploads(files: list[UploadFile]) -> list[Upload]:
    """Each file's bytes, reading at most one byte past the limit so a huge file is not loaded."""
    result = []
    for file in files:
        data = file.file.read(MAX_BYTES + 1)
        name = file.filename or "file"
        if len(data) > MAX_BYTES:
            raise HTTPException(400, f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB.")
        result.append(Upload(name, data))
    return result


def file_out(chat_id: int, stored_name: str, size: int | None = None) -> FileOut:
    return FileOut(
        stored_name=stored_name,
        name=stored_name.split("-", 1)[-1],
        url=f"/api/publisher/sessions/{chat_id}/files/{stored_name}",
        size=size,
    )


@router.post("/sessions", response_model=TurnOut)
def start(request: Request, text: Text = "", files: Files = []) -> TurnOut:  # noqa: B006
    uploads = read_uploads(files)
    return turn_out(run(lambda: service(request).start(text, uploads)))


@router.post("/sessions/{chat_id}/messages", response_model=TurnOut)
def send(chat_id: int, request: Request, text: Text = "", files: Files = []) -> TurnOut:  # noqa: B006
    uploads = read_uploads(files)
    return turn_out(run(lambda: service(request).send(chat_id, text, uploads)))


@router.get("/sessions/{chat_id}/files/{stored_name}")
def download(chat_id: int, stored_name: str, request: Request) -> FileResponse:
    path = run(lambda: service(request).file_path(chat_id, stored_name))
    return FileResponse(path, filename=stored_name.split("-", 1)[-1])


@router.post("/sessions/{chat_id}/confirm", response_model=ConfirmOut)
def confirm(chat_id: int, request: Request) -> ConfirmOut:
    done = run(lambda: service(request).confirm(chat_id))
    site = request.app.state.settings.jira_site_url
    return ConfirmOut(
        chat_id=done.chat_id,
        record_id=done.record_id,
        ok=done.result.ok,
        created=[
            CreatedOut(
                kind=c.kind,
                key=c.key,
                summary=c.summary,
                parent=c.parent,
                url=f"{site}/browse/{c.key}",
            )
            for c in done.result.created
        ],
        error=done.result.error,
        mismatches=done.result.mismatches,
    )


@router.get("/sessions", response_model=list[ChatSummaryOut])
def list_chats(request: Request) -> list[ChatSummaryOut]:
    return [
        ChatSummaryOut(
            chat_id=c.chat_id,
            display_id=display_id(c.chat_id),
            created_at=c.created_at,
            title=c.title,
            created_keys=c.created_keys,
        )
        for c in run(lambda: service(request).list_chats())
    ]


@router.get("/sessions/{chat_id}", response_model=ChatOut)
def open_chat(chat_id: int, request: Request) -> ChatOut:
    view = run(lambda: service(request).open_chat(chat_id))
    return ChatOut(
        chat_id=view.chat_id,
        display_id=display_id(view.chat_id),
        created_at=view.created_at,
        transcript_available=view.bubbles is not None,
        bubbles=[
            BubbleOut(
                role=b.role,
                text=b.text,
                timestamp=b.timestamp,
                plan=_plan(b.plan),
                files=[file_out(view.chat_id, name) for name in b.files],
            )
            for b in view.bubbles or []
        ],
        proposal_id=view.proposal_id,
        proposal=view.proposal,
        records=[
            RecordOut(
                record_id=r.id,
                confirmed_at=r.confirmed_at,
                plan=r.proposed_items if isinstance(r.proposed_items, dict) else None,
                created_keys=[k for k in (r.created_keys or "").split(",") if k],
            )
            for r in view.records
        ],
        files=[file_out(view.chat_id, f.stored_name, f.size) for f in view.files],
    )
