"""The Publisher use cases: chats, proposals, Confirm and Previous Chats.

The agent work (running the Publisher, checking its plan, creating in Jira, reading a transcript)
is in pipeline.publisher. This service adds what needs the database:
- a chat is a chat_sessions row, shown as PUB-000001, holding Claude's session id;
- a checked plan is a publish_records row without confirmed_at: the proposal Confirm creates.
  Any new message withdraws it, because the agent may change the plan in its answer;
- Confirm stores the confirm time and the created keys (in creation order: each Story, then its
  Sub-tasks), and the agent is told what was created before the user's next message;
- one message or Confirm at a time per chat, because a Claude session cannot take two at once;
- attached documents: their text goes into the message (pipeline.publisher.attachments) and the
  original files are kept in <BRIGADE_DATA_DIR>/uploads/PUB-000001/, after the agent answered.
"""

import json
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from core.db import get_session
from core.db.models import ChatSession, Project, PublishRecord
from core.db.repositories.projects import sync_env_project
from core.files import uploads
from core.files.extract import FileRejected, extract_text
from core.settings import Settings
from core.trackers.jira.client import JiraClient
from pipeline.publisher.attachments import message_with_files
from pipeline.publisher.chat import MAX_MESSAGE_CHARS, REPO_ROOT, PublisherChat, Turn
from pipeline.publisher.guard import parse_plan
from pipeline.publisher.publish import NOTE_START, Created, PublishResult, created_note, publish
from pipeline.publisher.transcript import CLAUDE_HOME, Bubble, find_transcript, read_chat
from pipeline.runner.claude_runner import AgentRunner

CHAT_PREFIX = "PUB-"
MAX_LISTED_CHATS = 100
TITLE_CHARS = 80
MAX_FILES = 5  # per message


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


class PublisherService:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        runner: AgentRunner,
        client_factory: Callable[[Settings], JiraClient] = JiraClient.from_settings,
        claude_home: Path = CLAUDE_HOME,
        cwd: Path = REPO_ROOT,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._client_factory = client_factory
        self._claude_home = claude_home
        self._cwd = cwd
        self._now = now
        self._uploads_dir = settings.data_dir / "uploads"
        self._chat = PublisherChat(settings, runner, client_factory, repo_root=cwd)
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ---------- use cases ----------

    def start(self, message: str, files: list[Upload] | None = None) -> TurnResult:
        """A new chat. The row and the files are written only after the agent answered, so a
        failed start leaves nothing behind."""
        self._project_id()  # fail early when .env names no project
        prepared = self._prepare(message, files or [], already=0)
        turn = self._chat.send(message_with_files(message, [(n, t) for n, t, _ in prepared]))
        with get_session(self._engine) as session:
            row = ChatSession(
                project_id=self._project_id(session),
                claude_session_id=turn.session_id,
                created_at=self._now(),
            )
            session.add(row)
            session.flush()
            chat_id = row.id
        self._save_files(chat_id, prepared)
        return TurnResult(chat_id, turn, self._keep_proposal(chat_id, turn))

    def send(self, chat_id: int, message: str, files: list[Upload] | None = None) -> TurnResult:
        with self._lock(chat_id):
            with get_session(self._engine) as session:
                row = self._chat_row(session, chat_id)
                session_id = row.claude_session_id
            already = len(uploads.list_files(self._uploads_dir, chat_id))
            prepared = self._prepare(message, files or [], already)
            prompt = message_with_files(message, [(n, t) for n, t, _ in prepared])
            with get_session(self._engine) as session:
                withdraw_open_proposal(session, chat_id)
                note = self._untold_note(session, chat_id, session_id)
            if note and prompt:
                prompt = f"{note}\n\n{prompt}"
            turn = self._chat.send(prompt, session_id)
            self._save_files(chat_id, prepared)
            return TurnResult(chat_id, turn, self._keep_proposal(chat_id, turn))

    def file_path(self, chat_id: int, stored_name: str) -> Path:
        with get_session(self._engine) as session:
            self._chat_row(session, chat_id)
        path = uploads.find(self._uploads_dir, chat_id, stored_name)
        if path is None:
            raise NotFound(f"{stored_name} is not a file of {display_id(chat_id)}.")
        return path

    def confirm(self, chat_id: int) -> ConfirmResult:
        with self._lock(chat_id):
            with get_session(self._engine) as session:
                self._chat_row(session, chat_id)
                record = open_proposal(session, chat_id)
                if record is None:
                    raise Conflict("There is no proposal to confirm. Ask the Publisher first.")
                record.confirmed_at = self._now()  # taken now, so it cannot be confirmed twice
                record_id, items = record.id, record.proposed_items
            parsed = parse_plan(json.dumps(items))
            if parsed.plan is None or parsed.problems:  # cannot happen for a stored proposal
                result = PublishResult(error="The stored proposal is not a valid plan.")
            else:
                client = self._client_factory(self._settings)
                try:
                    result = publish(parsed.plan, client, self._settings.jira_project_key)
                finally:
                    client.close()
            with get_session(self._engine) as session:
                record = session.get(PublishRecord, record_id)
                if record is None:
                    raise Conflict("The proposal record no longer exists.")
                if not result.created:  # nothing exists in Jira: the proposal is withdrawn
                    session.delete(record)
                    record_id = None
                else:
                    record.created_keys = ",".join(result.keys)
            return ConfirmResult(chat_id, record_id, result)

    def list_chats(self) -> list[ChatSummary]:
        with get_session(self._engine) as session:
            rows = session.scalars(
                select(ChatSession)
                .where(ChatSession.project_id == self._project_id(session))
                .order_by(ChatSession.id.desc())
                .limit(MAX_LISTED_CHATS)
            ).all()
            keys = {row.id: confirmed_keys(session, row.id) for row in rows}
        summaries = []
        for row in rows:
            bubbles = self._bubbles(row.claude_session_id)
            first = next((b.text for b in bubbles or [] if b.role == "user"), None)
            title = " ".join(first.split())[:TITLE_CHARS] if first else None
            summaries.append(ChatSummary(row.id, row.created_at, title, keys[row.id]))
        return summaries

    def open_chat(self, chat_id: int) -> ChatView:
        with get_session(self._engine) as session:
            row = self._chat_row(session, chat_id)
            proposal = open_proposal(session, chat_id)
            records = list(
                session.scalars(
                    select(PublishRecord)
                    .where(
                        PublishRecord.chat_session_id == chat_id,
                        PublishRecord.confirmed_at.is_not(None),
                    )
                    .order_by(PublishRecord.id)
                )
            )
            session_id, created_at = row.claude_session_id, row.created_at
        return ChatView(
            chat_id,
            created_at,
            self._bubbles(session_id),
            proposal.id if proposal else None,
            proposal.proposed_items
            if proposal and isinstance(proposal.proposed_items, dict)
            else None,
            records,
            uploads.list_files(self._uploads_dir, chat_id),
        )

    # ---------- helpers ----------

    def _project_id(self, session: Session | None = None) -> int:
        if session is None:
            with get_session(self._engine) as own:
                return self._project_id(own)
        project: Project | None = sync_env_project(session, self._settings)
        if project is None:
            raise PublisherError("No project: BRIGADE_PROJECT_PATH is empty in .env.")
        return project.id

    def _chat_row(self, session: Session, chat_id: int) -> ChatSession:
        row = session.get(ChatSession, chat_id)
        if row is None or row.project_id != self._project_id(session):
            raise NotFound(f"Chat {display_id(chat_id)} was not found in this project.")
        return row

    def _prepare(
        self, message: str, files: list[Upload], already: int
    ) -> list[tuple[str, str, bytes]]:
        """(stored name, text, original bytes) of each attached file, read before the agent
        runs, so a bad file is refused without spending a turn."""
        if len(files) > MAX_FILES:
            raise PublisherError(f"At most {MAX_FILES} files can be attached to one message.")
        try:
            texts = [extract_text(f.name, f.data) for f in files]
        except FileRejected as exc:
            raise PublisherError(str(exc)) from None
        if len(message) + sum(len(t) for t in texts) > MAX_MESSAGE_CHARS:
            raise PublisherError("The attached documents are too long together; send fewer.")
        names = uploads.stored_names([f.name for f in files], already)
        return [(n, t, f.data) for n, t, f in zip(names, texts, files, strict=True)]

    def _save_files(self, chat_id: int, prepared: list[tuple[str, str, bytes]]) -> None:
        for stored_name, _text, data in prepared:
            uploads.save(self._uploads_dir, chat_id, stored_name, data)

    def _keep_proposal(self, chat_id: int, turn: Turn) -> int | None:
        if turn.plan is None:
            return None
        with get_session(self._engine) as session:
            record = PublishRecord(chat_session_id=chat_id, proposed_items=turn.plan.as_dict())
            session.add(record)
            session.flush()
            return record.id

    def _untold_note(self, session: Session, chat_id: int, session_id: str) -> str | None:
        """What the last Confirm created, unless the agent was already told (in its transcript)."""
        record = session.scalars(
            select(PublishRecord)
            .where(
                PublishRecord.chat_session_id == chat_id,
                PublishRecord.confirmed_at.is_not(None),
            )
            .order_by(PublishRecord.id.desc())
        ).first()
        if record is None or not record.created_keys:
            return None
        keys = record.created_keys.split(",")
        path = find_transcript(session_id, self._cwd, self._claude_home)
        if path is not None:
            text = path.read_text(encoding="utf-8", errors="replace")
            if NOTE_START in text and f" {keys[0]} under " in text:
                return None
        return created_note(PublishResult(created=_created_from(record, keys)))

    def _bubbles(self, session_id: str) -> list[Bubble] | None:
        try:
            return read_chat(session_id, self._cwd, self._claude_home)
        except (OSError, ValueError):
            return None

    @contextmanager
    def _lock(self, chat_id: int) -> Generator[None, None, None]:
        with self._locks_guard:
            lock = self._locks.setdefault(chat_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise Conflict("The Publisher is still answering in this chat. Wait for it.")
        try:
            yield
        finally:
            lock.release()


def open_proposal(session: Session, chat_id: int) -> PublishRecord | None:
    return session.scalars(
        select(PublishRecord)
        .where(PublishRecord.chat_session_id == chat_id, PublishRecord.confirmed_at.is_(None))
        .order_by(PublishRecord.id.desc())
    ).first()


def withdraw_open_proposal(session: Session, chat_id: int) -> None:
    session.execute(
        delete(PublishRecord).where(
            PublishRecord.chat_session_id == chat_id, PublishRecord.confirmed_at.is_(None)
        )
    )


def confirmed_keys(session: Session, chat_id: int) -> list[str]:
    values = session.scalars(
        select(PublishRecord.created_keys)
        .where(PublishRecord.chat_session_id == chat_id, PublishRecord.created_keys.is_not(None))
        .order_by(PublishRecord.id)
    )
    return [key for value in values for key in (value or "").split(",") if key]


def _created_from(record: PublishRecord, keys: list[str]) -> list[Created]:
    """The created items again, from the stored plan and keys (same order as creation)."""
    items: list[Created] = []
    plan = record.proposed_items
    if not isinstance(plan, dict):
        return items
    stories = plan.get("stories") or []
    remaining = iter(keys)
    for story in stories:
        story_key = next(remaining, None)
        if story_key is None:
            break
        items.append(Created("story", story_key, story["summary"], story["epic"]))
        for subtask in story.get("subtasks") or []:
            key = next(remaining, None)
            if key is None:
                return items
            items.append(Created("sub-task", key, subtask["summary"], story_key))
    return items
