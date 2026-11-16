"""One-line titles and summaries for an agent's tool calls and their results."""

import json
import re
from typing import Any

MAX_TITLE = 160
FILE_TOOLS = ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit")


def one_line(text: str, limit: int = MAX_TITLE) -> str:
    """The first non-empty line, cut to `limit` characters."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first if len(first) <= limit else first[: limit - 1] + "…"


def last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return one_line(lines[-1]) if lines else ""


class PathTrimmer:
    """Shows paths inside the agent's working folder relative to it."""

    def __init__(self) -> None:
        self.root: str | None = None

    def set_root(self, cwd: object) -> None:
        if isinstance(cwd, str) and cwd:
            self.root = cwd.replace("\\", "/").rstrip("/") + "/"

    def in_text(self, text: str) -> str:
        """`text` with the folder's path, written either way round, taken out."""
        if not self.root:
            return text
        for root in {self.root, self.root.replace("/", "\\")}:
            text = re.sub(re.escape(root), "", text, flags=re.IGNORECASE)
        return text

    def __call__(self, value: object) -> str:
        text = str(value)
        normal = text.replace("\\", "/")
        if self.root and normal.lower().startswith(self.root.lower()):
            return normal[len(self.root) :]
        return text


def _file_title(name: str, data: dict[str, Any], trim: PathTrimmer) -> str:
    title = trim(data.get("file_path") or data.get("notebook_path") or data.get("path"))
    if name == "Write" and isinstance(data.get("content"), str):
        title += f" ({len(data['content'].splitlines())} lines)"
    if name == "MultiEdit" and isinstance(data.get("edits"), list):
        title += f" ({len(data['edits'])} edits)"
    return title


def tool_title(name: str, data: dict[str, Any], trim: PathTrimmer) -> str:
    if name in FILE_TOOLS and (
        data.get("file_path") or data.get("notebook_path") or data.get("path")
    ):
        return _file_title(name, data, trim)
    if name == "Bash" and data.get("command"):
        return one_line(str(data["command"]))
    if name == "Grep" and data.get("pattern"):
        where = trim(data.get("path") or data.get("glob") or "")
        return str(data["pattern"]) + (f"  in {where}" if where else "")
    if name == "Glob" and data.get("pattern"):
        return str(data["pattern"])
    for key in ("description", "url", "query", "prompt"):
        if isinstance(data.get(key), str):
            return one_line(data[key])
    return one_line(json.dumps(data, ensure_ascii=False)) if data else ""


def _edits_detail(edits: list[Any]) -> str:
    parts = []
    for number, edit in enumerate(edits, 1):
        if isinstance(edit, dict):
            parts.append(
                f"--- edit {number}, before\n{edit.get('old_string', '')}\n"
                f"+++ edit {number}, after\n{edit.get('new_string', '')}"
            )
    return "\n\n".join(parts)


def tool_detail(name: str, data: dict[str, Any]) -> str:
    """What the call did, in full: a before/after for edits, the content for a write."""
    if name == "Edit":
        return f"--- before\n{data.get('old_string', '')}\n+++ after\n{data.get('new_string', '')}"
    if name == "MultiEdit" and isinstance(data.get("edits"), list):
        return _edits_detail(data["edits"])
    if name == "Write":
        return str(data.get("content", ""))
    if name == "Bash":
        text = str(data.get("command", ""))
        return text + (f"\n\n# {data['description']}" if data.get("description") else "")
    return json.dumps(data, ensure_ascii=False, indent=2)


def result_text(content: object) -> str:
    """A tool result's text, whether Claude sent a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, dict) and block.get("type") == "image":
                parts.append("[image]")
        return "\n".join(parts)
    return "" if content is None else json.dumps(content, ensure_ascii=False)


def result_summary(tool: str | None, text: str, status: str) -> str:
    if status != "ok":
        return one_line(text) or status
    if not text.strip():
        return "(no output)"
    if tool == "Read":
        return f"{len(text.splitlines())} lines"
    if tool in ("Grep", "Glob"):
        lines = [line for line in text.splitlines() if line.strip()]
        return one_line(lines[0]) if len(lines) == 1 else f"{len(lines)} lines of matches"
    return last_line(text) if tool == "Bash" else one_line(text)
