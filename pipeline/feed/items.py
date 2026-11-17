"""The one shape every source is turned into, and how it is cut and masked for the page.

An item is one thing that happened: an agent said something or called a tool (paired with that
tool's result), or the orchestrator ran a step (paired with its outcome, so a running step shows
as pending until it ends).
"""

from dataclasses import dataclass, field
from typing import Any

from core.masking import mask_secrets

HEAD_LINES = 40
TAIL_LINES = 40
MAX_DETAIL_CHARS = 16_000
MAX_FULL_CHARS = 2_000_000


def shorten(text: str, *, full: bool = False) -> tuple[str, bool]:
    """`text` cut to its first and last lines unless `full`; True when anything was cut."""
    if full:
        return (text, False) if len(text) <= MAX_FULL_CHARS else (text[:MAX_FULL_CHARS], True)
    cut = False
    lines = text.split("\n")
    if len(lines) > HEAD_LINES + TAIL_LINES:
        hidden = len(lines) - HEAD_LINES - TAIL_LINES
        lines = [*lines[:HEAD_LINES], f"... {hidden} lines hidden ...", *lines[-TAIL_LINES:]]
        cut = True
    text = "\n".join(lines)
    if len(text) > MAX_DETAIL_CHARS:
        half = MAX_DETAIL_CHARS // 2
        hidden_chars = len(text) - MAX_DETAIL_CHARS
        text = f"{text[:half]}\n... {hidden_chars} characters hidden ...\n{text[-half:]}"
        cut = True
    return text, cut


def _safe(text: str, full: bool) -> tuple[str, bool]:
    """Masked first, then shortened, so a secret on the cut edge is never left half visible."""
    return shorten(mask_secrets(text), full=full)


@dataclass
class Item:
    index: int
    kind: str  # start, say, think, tool, finish, step, error
    title: str
    detail: str = ""
    at: str | None = None
    tool: str | None = None
    status: str | None = None  # for steps: ok, error, warn
    result: dict[str, Any] | None = None  # the outcome; None while waiting for it
    awaits_result: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def pending(self) -> bool:
        return self.awaits_result and self.result is None

    def to_dict(self, *, full: bool = False) -> dict[str, Any]:
        """The item as the page gets it: every text masked, long ones shortened."""
        detail, cut = _safe(self.detail, full)
        data: dict[str, Any] = {
            "index": self.index,
            "kind": self.kind,
            "title": mask_secrets(self.title),
            "detail": detail,
            "truncated": cut,
            "at": self.at,
            "tool": self.tool,
            "status": self.status,
            "pending": self.pending,
            "result": None,
        }
        if self.result is not None:
            result_detail, result_cut = _safe(str(self.result.get("detail", "")), full)
            data["result"] = {
                "status": self.result.get("status", "ok"),
                "summary": mask_secrets(str(self.result.get("summary", ""))),
                "detail": result_detail,
                "truncated": result_cut,
                "at": self.result.get("at"),
            }
            data["truncated"] = cut or result_cut
        return data


def stable_index(items: list[Item]) -> int:
    """Items before this index will not change any more; a reader asks again from here."""
    return next((item.index for item in items if item.pending), len(items))


def feed(items: list[Item], after: int = 0, *, full: bool = False) -> dict[str, Any]:
    """The items from `after` on, as the page gets them; `full` lifts the cut on long texts."""
    after = max(0, min(after, len(items)))
    return {
        "items": [item.to_dict(full=full) for item in items[after:]],
        "from": after,
        "next": stable_index(items),
        "count": len(items),
    }
