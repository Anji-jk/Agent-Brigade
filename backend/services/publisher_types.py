"""What the Publisher service hands back, and the errors it raises (each knows its HTTP status)."""

from dataclasses import dataclass
from datetime import datetime

from core.db.models import PublishRecord
from core.files import uploads
from pipeline.publisher.chat import Turn
from pipeline.publisher.publish import PublishResult
from pipeline.publisher.transcript import Bubble

CHAT_PREFIX = "PUB-"


class PublisherError(Exception):
    status = 400


class NotFound(PublisherError):
    status = 404


class Conflict(PublisherError):
    status = 409


def display_id(chat_id: int) -> str:
    return f"{CHAT_PREFIX}{chat_id:06d}"


@dataclass(frozen=True)
class Upload:
    name: str  # as the user's computer named it
    data: bytes


@dataclass(frozen=True)
class TurnResult:
    chat_id: int
    turn: Turn
    proposal_id: int | None


@dataclass(frozen=True)
class ConfirmResult:
    chat_id: int
    record_id: int | None  # None when nothing was created
    result: PublishResult


@dataclass(frozen=True)
class ChatSummary:
    chat_id: int
    created_at: datetime | None
    title: str | None  # the first message, or None when the transcript was deleted
    created_keys: list[str]


@dataclass(frozen=True)
class ChatView:
    chat_id: int
    created_at: datetime | None
    bubbles: list[Bubble] | None  # None: Claude Code deleted the transcript
    proposal_id: int | None
    proposal: dict | None
    records: list[PublishRecord]  # confirmed, oldest first
    files: list[uploads.StoredFile]  # every document attached in this chat
