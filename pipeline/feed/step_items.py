"""The orchestrator's own logs as items: one attempt's steps and the story loop's log.

An attempt's `events.jsonl` has lines like {"at", "step": "builder_started", ...}. A step that
takes time is written twice, `builder_started` and later `builder_finished`; the two become one
item that is pending until the second arrives. The story log (`story-events.jsonl`) has lines
like {"at", "kind": "task_merged", "key": "SMT-62", ...} and is one item per line.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipeline.feed.items import Item
from pipeline.feed.readers import json_lines
from pipeline.feed.tool_text import one_line

STARTS = {
    "builder_started": "builder",
    "tester_started": "tester",
    "judge_started": "judge",
    "merge_started": "merge into the story branch",
}
ENDINGS = {
    "builder_finished": "builder_started",
    "tester_finished": "tester_started",
    "judge_finished": "judge_started",
    "merge_finished": "merge_started",
}


def _count(number: int, word: str) -> str:
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def _lines(values: object) -> str:
    return "\n".join(f"- {value}" for value in values) if isinstance(values, list) else ""


def _usage(entry: dict[str, Any]) -> list[str]:
    parts = []
    if isinstance(entry.get("cost_usd"), int | float):
        parts.append(f"${entry['cost_usd']:.4f}")
    if isinstance(entry.get("turns"), int):
        parts.append(f"{entry['turns']} turns")
    if isinstance(entry.get("seconds"), int | float):
        parts.append(f"{entry['seconds']:.1f}s")
    return parts


def _builder_outcome(entry: dict[str, Any]) -> dict[str, Any]:
    if not entry.get("ok"):
        error = str(entry.get("error") or "")
        return {"status": "error", "summary": one_line(error) or "failed", "detail": error}
    changed = entry.get("changed")
    files = [_count(changed, "file") + " changed"] if isinstance(changed, int) else []
    return {"status": "ok", "summary": " · ".join([*files, *_usage(entry)]) or "done"}


def _tester_outcome(entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("error"):
        error = str(entry["error"])
        return {"status": "error", "summary": one_line(error), "detail": error}
    wrote = entry.get("wrote")
    files = [_count(wrote, "test file") + " written"] if isinstance(wrote, int) else []
    return {"status": "ok", "summary": " · ".join([*files, *_usage(entry)]) or "done"}


def _judge_outcome(entry: dict[str, Any]) -> dict[str, Any]:
    outcome = str(entry.get("outcome"))
    summary = outcome + (f" · verdict {entry['verdict']}" if entry.get("verdict") else "")
    commit = f"\ncommit: {entry['commit']}" if entry.get("commit") else ""
    return {
        "status": "ok" if outcome == "done" else "error",
        "summary": summary,
        "detail": _lines(entry.get("reasons")) + commit,
    }


def _merge_outcome(entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("merged"):
        return {"status": "ok", "summary": f"merged · {entry.get('how')}"}
    error = str(entry.get("error") or "")
    return {"status": "error", "summary": "not merged", "detail": error}


OUTCOMES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "builder_finished": _builder_outcome,
    "tester_finished": _tester_outcome,
    "judge_finished": _judge_outcome,
    "merge_finished": _merge_outcome,
}


def _start_detail(entry: dict[str, Any]) -> str:
    lines = [f"model: {entry['model']}"] if entry.get("model") else []
    return "\n".join(
        [*lines, f"session: {entry['session_id']}"] if entry.get("session_id") else lines
    )


def _single(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Kind, title, detail and status of a step that is written once."""
    if name == "attempt_started":
        return {"kind": "start", "title": f"attempt {entry.get('attempt')} started"}
    if name == "worktree_ready":
        ok = entry.get("setup_ok") is not False
        title = f"worktree ready on {entry.get('branch')}"
        return {
            "kind": "step",
            "title": title if ok else title + ", setup failed",
            "status": "ok" if ok else "error",
        }
    if name == "checks_finished":
        passed = bool(entry.get("passed"))
        return {
            "kind": "step",
            "title": "checks passed" if passed else "checks failed",
            "detail": _lines(entry.get("failures")),
            "status": "ok" if passed else "error",
        }
    if name == "tester_finished":  # the tester is only written once when it did not run
        return {
            "kind": "step",
            "title": "tester skipped",
            "detail": str(entry.get("skipped") or ""),
            "status": "skipped",
        }
    rest = {k: v for k, v in entry.items() if k not in ("at", "step")}
    return {
        "kind": "step",
        "title": name.replace("_", " "),
        "detail": json.dumps(rest, ensure_ascii=False, indent=2),
    }


def _make(index: int, entry: dict[str, Any], **fields: Any) -> Item:
    at = entry.get("at")
    return Item(index=index, at=at if isinstance(at, str) else None, **fields)


def _skipped(name: str, entry: dict[str, Any]) -> bool:
    """A tester_finished that says the tester did not run: it has no tester_started before it."""
    return name == "tester_finished" and entry.get("ran") is False


def orchestrator_items(path: Path) -> list[Item]:
    """The readable story of one attempt's steps."""
    items: list[Item] = []
    waiting: dict[str, Item] = {}
    for _, entry in json_lines(path):
        name = entry.get("step")
        if not isinstance(name, str):
            continue
        if name in ENDINGS and not _skipped(name, entry):
            started = waiting.pop(ENDINGS[name], None)
            if started is not None:
                started.result = {**OUTCOMES[name](entry), "at": entry.get("at")}
                continue
            # a finish whose start is not in the log: shown on its own, with its outcome
            item = _make(
                len(items), entry, kind="step", title=STARTS[ENDINGS[name]], extra={"step": name}
            )
            item.result = {**OUTCOMES[name](entry), "at": entry.get("at")}
        elif name in STARTS:
            item = _make(
                len(items),
                entry,
                kind="step",
                title=STARTS[name],
                detail=_start_detail(entry),
                awaits_result=True,
            )
            waiting[name] = item
        else:
            item = _make(len(items), entry, extra={"step": name}, **_single(name, entry))
        items.append(item)
    return items


def _story_fields(kind: str, entry: dict[str, Any]) -> dict[str, Any]:
    who = f"{entry.get('key')} · attempt {entry.get('attempt')}"
    statuses = "\n".join(f"{k}: {v}" for k, v in entry.items() if k not in ("kind", "at"))
    table: dict[str, dict[str, Any]] = {
        "story_started": {
            "kind": "start",
            "title": (
                f"story started · {_count(int(entry.get('tasks') or 0), 'task')}, "
                f"up to {entry.get('parallel')} at once"
            ),
        },
        "task_started": {"kind": "step", "title": f"{who} started"},
        "task_done": {"kind": "step", "title": f"{who} built and judged: done"},
        "task_merged": {
            "kind": "finish",
            "title": f"{entry.get('key')} · merged ({entry.get('how')})",
        },
        "task_failed": {"kind": "error", "title": f"{who} failed: {entry.get('reason')}"},
        "task_stopped": {
            "kind": "error",
            "title": f"{entry.get('key')} · stopped: {entry.get('status')}",
            "detail": str(entry.get("detail") or ""),
        },
        "story_finished": {"kind": "finish", "title": "story finished", "detail": statuses},
        "story_stopped": {"kind": "error", "title": "story stopped", "detail": statuses},
    }
    if kind in table:
        return table[kind]
    rest = {k: v for k, v in entry.items() if k not in ("kind", "at")}
    return {
        "kind": "step",
        "title": kind.replace("_", " "),
        "detail": json.dumps(rest, ensure_ascii=False, indent=2),
    }


def story_items(path: Path) -> list[Item]:
    """The readable story of the whole loop: one item per line of story-events.jsonl."""
    items = []
    for _, entry in json_lines(path):
        fields = _story_fields(str(entry.get("kind")), entry)
        status = {"finish": "ok", "error": "error"}.get(fields["kind"])
        extra = {"key": entry["key"]} if "key" in entry else {}
        items.append(_make(len(items), entry, status=status, extra=extra, **fields))
    return items
