"""A previous Publisher chat, read back from Claude Code's own transcript.

Claude Code keeps every session as ~/.claude/projects/<folder>/<session id>.jsonl, where <folder>
is the working directory with every character other than a letter or digit replaced by '-'.
Brigade always runs the agent from the Agent-Brigade folder, so all Publisher chats are there.
Claude Code deletes transcripts after cleanupPeriodDays (30 by default): then read_chat returns
None and the caller shows what was created from the publish record instead.

    python -m pipeline.publisher.transcript <session id>

Only what a person saw in the chat becomes a bubble: the user's messages (an attached document
as its file name, not its text), and the Publisher's final answer of each turn without its plan
block. Tool calls and their output, the agent's notes between tool calls, thinking, Brigade's own
correction messages and its note of what Confirm created are left out. When Brigade asked the
agent to fix its plan, the corrected answer replaces the refused one, as in the live chat.
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pipeline.publisher.attachments import split_files
from pipeline.publisher.chat import REPO_ROOT, SYSTEM_MARKER
from pipeline.publisher.guard import find_plan_block, without_plan_block
from pipeline.publisher.publish import NOTE_END, NOTE_START

CLAUDE_HOME = Path.home() / ".claude"
SESSION_PATTERN = re.compile(r"^[0-9a-fA-F-]{8,64}$")


@dataclass(frozen=True)
class Bubble:
    role: str  # "user" or "publisher"
    text: str
    timestamp: str | None = None
    plan: str | None = None  # the raw plan block of this answer, if it had one
    files: tuple[str, ...] = ()  # stored names of documents attached to a user message


def project_folder_name(cwd: Path | str) -> str:
    """Claude Code's folder name for a working directory."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def find_transcript(
    session_id: str, cwd: Path = REPO_ROOT, claude_home: Path = CLAUDE_HOME
) -> Path | None:
    """The transcript file of a session, or None if Claude Code has none (or deleted it)."""
    if not SESSION_PATTERN.match(session_id):
        raise ValueError(f"'{session_id}' is not a Claude session id.")
    projects = claude_home / "projects"
    expected = projects / project_folder_name(cwd) / f"{session_id}.jsonl"
    if expected.is_file():
        return expected
    # Long folder names are shortened by Claude Code; look one level down, never deeper.
    try:
        folders = [f for f in projects.iterdir() if f.is_dir()]
    except OSError:
        return None
    for folder in folders:
        candidate = folder / f"{session_id}.jsonl"
        try:
            if candidate.is_file():
                return candidate
        except OSError:  # unreadable folder names exist on Windows; skip them
            continue
    return None


def _texts(content: object) -> list[str]:
    """The text blocks of a message (a plain string counts as one block), with \n line ends:
    chats sent before the runner kept line ends were stored with \r\n on Windows."""
    if isinstance(content, str):
        blocks = [content]
    elif isinstance(content, list):
        blocks = [
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
    else:
        return []
    return [b.replace("\r\n", "\n") for b in blocks]


def _is_tool_result(content: object) -> bool:
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def _records(lines: list[str]) -> list[dict]:
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:  # a half-written last line while the agent is still running
            continue
        if isinstance(record, dict) and not record.get("isSidechain"):
            records.append(record)
    return records


class _Builder:
    """Collects bubbles while the transcript records are read in order."""

    def __init__(self) -> None:
        self.bubbles: list[Bubble] = []
        self._answer_id: str | None = None  # the assistant message whose text is the answer
        self._answer: list[str] = []
        self._answer_time: str | None = None
        self._replaces_last = False  # the next answer replaces the last (after a fix request)

    def user(self, record: dict, content: object) -> None:
        if record.get("isMeta") or _is_tool_result(content):
            return
        self.close_answer()
        text = "\n\n".join(_texts(content)).strip()
        if text.startswith(NOTE_START) and NOTE_END in text:  # what Confirm created: not typed
            text = text.split(NOTE_END, 1)[1].strip()
        if text.startswith(SYSTEM_MARKER):
            self._replaces_last = True
        elif text:
            typed, files = split_files(text)
            self.bubbles.append(Bubble("user", typed, record.get("timestamp"), files=files))

    def assistant(self, record: dict, message: dict) -> None:
        texts = [t for t in _texts(message.get("content")) if t.strip()]
        if not texts:
            return
        message_id = str(message.get("id") or record.get("uuid"))
        if message_id != self._answer_id:  # a newer message: earlier notes were not the answer
            self._answer_id, self._answer = message_id, []
        self._answer.extend(texts)
        self._answer_time = record.get("timestamp")

    def close_answer(self) -> None:
        text = "\n\n".join(self._answer).strip()
        if text:
            bubble = Bubble(
                "publisher", without_plan_block(text), self._answer_time, find_plan_block(text)
            )
            if self._replaces_last and self.bubbles and self.bubbles[-1].role == "publisher":
                self.bubbles[-1] = bubble
            else:
                self.bubbles.append(bubble)
            self._replaces_last = False
        self._answer_id, self._answer, self._answer_time = None, [], None


def parse_transcript(lines: list[str]) -> list[Bubble]:
    """The chat as bubbles, from the lines of a transcript file."""
    builder = _Builder()
    for record in _records(lines):
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        if record.get("type") == "user" and message.get("role") == "user":
            builder.user(record, message.get("content"))
        elif record.get("type") == "assistant" and message.get("role") == "assistant":
            builder.assistant(record, message)
    builder.close_answer()
    return builder.bubbles


def read_chat(
    session_id: str, cwd: Path = REPO_ROOT, claude_home: Path = CLAUDE_HOME
) -> list[Bubble] | None:
    """The bubbles of a previous chat, or None if its transcript no longer exists."""
    path = find_transcript(session_id, cwd, claude_home)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_transcript(text.splitlines())


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python -m pipeline.publisher.transcript <session id>", file=sys.stderr)
        return 2
    try:
        bubbles = read_chat(args[0], REPO_ROOT, CLAUDE_HOME)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if bubbles is None:
        print("No transcript: Claude Code has no session with this id, or deleted it.")
        return 1
    for bubble in bubbles:
        plan = "  [+ plan]" if bubble.plan else ""
        print(f"--- {bubble.role} {bubble.timestamp or ''}{plan}\n{bubble.text}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
