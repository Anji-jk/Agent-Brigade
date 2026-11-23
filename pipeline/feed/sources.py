"""Which file of a run the page asks for, checked before any path is built.

The page sends a run id, a task key, an attempt number and a source name. They become folder and
file names, so nothing but the expected shapes is let through.
"""

import re
from pathlib import Path

from pipeline.feed.agent_stream import agent_items
from pipeline.feed.items import Item
from pipeline.feed.step_items import orchestrator_items, story_items
from pipeline.stages import attempt_log, events

ORCHESTRATOR = "orchestrator"
AGENTS = ("builder", "tester", "reviewer", "documenter", "doc-reviewer")
SOURCES = (ORCHESTRATOR, *AGENTS)
KEY = re.compile(r"[A-Z][A-Z0-9]*-[0-9]+")


class FeedError(ValueError):
    """The source, task key or attempt number asked for is not one that can exist."""


def _checked(key: object, number: object, source: object = ORCHESTRATOR) -> None:
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise FeedError(f"Not a task key: {key!r}")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise FeedError(f"Not an attempt number: {number!r}")
    if source not in SOURCES:
        raise FeedError(f"Not a source: {source!r}. Use one of {', '.join(SOURCES)}.")


def _path(root: Path, run_id: str, key: str, number: int, source: str) -> Path:
    if source == ORCHESTRATOR:
        return attempt_log.attempt_dir(root, run_id, key, number) / attempt_log.FILE
    return attempt_log.agent_events_path(root, run_id, key, number, source)


def attempt_items(root: Path, run_id: str, key: str, number: int, source: str) -> list[Item]:
    """One source of one attempt as items; none yet when the attempt has not written it."""
    _checked(key, number, source)
    path = _path(root, run_id, key, number, source)
    return orchestrator_items(path) if source == ORCHESTRATOR else agent_items(path)


def available(root: Path, run_id: str, key: str, number: int) -> list[str]:
    """The sources this attempt has written so far (a skipped Tester has no file, so no tab)."""
    _checked(key, number)
    return [s for s in SOURCES if _path(root, run_id, key, number, s).is_file()]


def story_log_items(root: Path, run_id: str) -> list[Item]:
    return story_items(events.events_path(root, run_id))
