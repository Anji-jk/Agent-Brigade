from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel


def _utc(value: datetime | None) -> datetime | None:
    """SQLite keeps no time zone; Brigade stores UTC, so say so, or the page shows UTC as local."""
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


UtcTime = Annotated[datetime | None, AfterValidator(_utc)]


class TurnOut(BaseModel):
    chat_id: int
    display_id: str  # PUB-000001
    reply: str  # the Publisher's answer, without the plan block
    plan: dict | None  # the checked plan waiting for Confirm
    counts: dict[str, int] | None  # {"stories": 1, "subtasks": 3}
    problems: list[str]  # why a plan in the answer was not accepted
    proposal_id: int | None
    cost_usd: float | None


class CreatedOut(BaseModel):
    kind: str  # story | sub-task
    key: str
    summary: str
    parent: str
    url: str


class ConfirmOut(BaseModel):
    chat_id: int
    record_id: int | None
    ok: bool
    created: list[CreatedOut]
    error: str | None
    mismatches: list[str]


class ChatSummaryOut(BaseModel):
    chat_id: int
    display_id: str
    created_at: UtcTime
    title: str | None  # first message; None when Claude Code deleted the transcript
    created_keys: list[str]


class FileOut(BaseModel):
    stored_name: str  # 01-requirements.docx
    name: str  # requirements.docx
    url: str  # download link
    size: int | None = None


class BubbleOut(BaseModel):
    role: str  # user | publisher
    text: str
    timestamp: str | None
    plan: dict | None  # the plan this answer proposed, for the plan tree
    files: list[FileOut]  # documents attached to this message


class RecordOut(BaseModel):
    record_id: int
    confirmed_at: UtcTime
    plan: dict | None
    created_keys: list[str]  # each Story, then its Sub-tasks, in the plan's order


class ChatOut(BaseModel):
    chat_id: int
    display_id: str
    created_at: UtcTime
    transcript_available: bool
    bubbles: list[BubbleOut]
    proposal_id: int | None  # the open proposal, if any
    proposal: dict | None
    records: list[RecordOut]  # what was created, oldest first
    files: list[FileOut]  # every document attached in this chat
