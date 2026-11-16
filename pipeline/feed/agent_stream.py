"""An agent's Claude stream (`claude -p --output-format stream-json --verbose`) as items.

The runner keeps the stream exactly as it arrived, one JSON event per line, with a `.times`
file beside it: Claude's own events carry no time, only assistant and user ones sometimes do.

Only what a person wants to follow is shown: the session start, what the agent said, each tool
call paired with its result, rate limits, and how the run ended. Hooks, task notices and other
system chatter are left out. Text from these files is untrusted (it holds whatever the agent
read); masking happens in `Item.to_dict`, not here.
"""

import json
from pathlib import Path
from typing import Any

from pipeline.feed.items import Item
from pipeline.feed.readers import json_lines, read_lines
from pipeline.feed.tool_text import (
    PathTrimmer,
    one_line,
    result_summary,
    result_text,
    tool_detail,
    tool_title,
)

BLOCKED_WORDS = ("permission", "not allowed", "denied", "requires approval", "was blocked")


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _money(value: object) -> str:
    return f"${value:.4f}" if isinstance(value, int | float) and not isinstance(value, bool) else ""


class AgentStory:
    """Builds the readable story of one agent, one event at a time."""

    def __init__(self, times: list[str]) -> None:
        self.times = times
        self.items: list[Item] = []
        self.tools: dict[str, Item] = {}
        self.seen: set[tuple[str, str]] = set()
        self.trim = PathTrimmer()
        self.started = False

    def add(self, kind: str, title: str, **kwargs: Any) -> Item:
        item = Item(index=len(self.items), kind=kind, title=title, **kwargs)
        self.items.append(item)
        return item

    def take(self, number: int, event: dict[str, Any]) -> None:
        stamp = event.get("timestamp")
        beside = self.times[number].strip() if number < len(self.times) else ""
        at = stamp if isinstance(stamp, str) and stamp else (beside or None)
        handler = {
            "system": self.system,
            "rate_limit_event": self.rate_limit,
            "assistant": self.assistant,
            "user": self.user,
            "result": self.result,
        }.get(str(event.get("type")))
        if handler is not None:
            handler(number, event, at)

    def system(self, number: int, event: dict[str, Any], at: str | None) -> None:
        if event.get("subtype") != "init":
            return
        self.trim.set_root(event.get("cwd"))
        tools = _list(event.get("tools"))
        model = event.get("model") or "default model"
        detail = "\n".join(
            filter(
                None,
                [
                    f"model: {model}",
                    f"working folder: {event['cwd']}" if event.get("cwd") else "",
                    f"permission mode: {event['permissionMode']}"
                    if event.get("permissionMode")
                    else "",
                    "tools: " + (", ".join(map(str, tools)) if tools else "none"),
                ],
            )
        )
        title = f"session started · {model} · {len(tools)} tools"
        self.add(
            "start", title if not self.started else "session woke up again", detail=detail, at=at
        )
        self.started = True

    def rate_limit(self, number: int, event: dict[str, Any], at: str | None) -> None:
        info = _dict(event.get("rate_limit_info"))
        status, kind = info.get("status"), info.get("rateLimitType", "limit")
        if status == "allowed_warning":
            self.add(
                "step", f"rate limit warning ({kind})", detail=_dump(info), at=at, status="warn"
            )
        elif status not in (None, "allowed"):
            self.add(
                "error",
                f"rate limited ({kind}: {status})",
                detail=_dump(info),
                at=at,
                status="error",
            )

    def assistant(self, number: int, event: dict[str, Any], at: str | None) -> None:
        message = _dict(event.get("message"))
        message_id = str(message.get("id") or f"line-{number}")
        for block in _list(message.get("content")):
            block = _dict(block)
            if block.get("type") == "tool_use":
                self._tool_call(block, message_id, at)
            elif block.get("type") in ("text", "thinking"):
                self._words(block, message_id, at)

    def _tool_call(self, block: dict[str, Any], message_id: str, at: str | None) -> None:
        tool_id = str(block.get("id") or f"{message_id}-{len(self.items)}")
        if ("tool", tool_id) in self.seen:
            return  # Claude repeats a message once per block it holds
        self.seen.add(("tool", tool_id))
        name, data = str(block.get("name") or "tool"), _dict(block.get("input"))
        self.tools[tool_id] = self.add(
            "tool",
            tool_title(name, data, self.trim),
            detail=tool_detail(name, data),
            at=at,
            tool=name,
            awaits_result=True,
        )

    def _words(self, block: dict[str, Any], message_id: str, at: str | None) -> None:
        said = block.get("type") == "text"
        text = str(block.get("text") if said else block.get("thinking") or "")
        if not text.strip() or (message_id, text) in self.seen:
            return
        self.seen.add((message_id, text))
        title = one_line(text)
        self.add(
            "say" if said else "think", title, detail=text if text.strip() != title else "", at=at
        )

    def user(self, number: int, event: dict[str, Any], at: str | None) -> None:
        for block in _list(_dict(event.get("message")).get("content")):
            block = _dict(block)
            if block.get("type") != "tool_result":
                continue
            text = result_text(block.get("content"))
            status = "ok"
            if block.get("is_error"):
                blocked = any(word in text.lower() for word in BLOCKED_WORDS)
                status = "blocked" if blocked else "error"
            owner = self.tools.get(str(block.get("tool_use_id")))
            summary = result_summary(owner.tool if owner else None, text, status)
            result = {
                "status": status,
                "detail": text,
                "at": at,
                "summary": self.trim.in_text(summary),
            }
            if owner is not None and owner.result is None:
                owner.result = result
            else:
                self.add("tool", "result of an earlier call", result=result, at=at)

    def result(self, number: int, event: dict[str, Any], at: str | None) -> None:
        failed = bool(event.get("is_error")) or event.get("subtype") not in (None, "success")
        parts = ["error: " + str(event.get("subtype")) if failed else "succeeded"]
        if isinstance(event.get("num_turns"), int):
            parts.append(f"{event['num_turns']} turns")
        if _money(event.get("total_cost_usd")):
            parts.append(_money(event["total_cost_usd"]) + " total")
        if isinstance(event.get("duration_ms"), int | float):
            parts.append(f"{event['duration_ms'] / 1000:.1f}s")
        self.add(
            "error" if failed else "finish",
            " · ".join(parts),
            detail=str(event.get("result") or ""),
            at=at,
            status="error" if failed else "ok",
        )


def agent_items(events_path: Path, times_path: Path | None = None) -> list[Item]:
    """The readable story of one agent. `times_path` defaults to the `.times` file beside it."""
    events_path = Path(events_path)
    if times_path is None:
        times_path = events_path.with_name(events_path.name.replace(".jsonl", ".times"))
    story = AgentStory(read_lines(times_path))
    for number, event in json_lines(events_path):
        story.take(number, event)
    return story.items
