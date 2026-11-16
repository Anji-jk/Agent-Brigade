"""Reading event files that may still be written to."""

import json
from pathlib import Path
from typing import Any


def read_lines(path: Path) -> list[str]:
    """The lines of a text file; none when it does not exist yet or cannot be read."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def json_lines(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """(line number, event) of every line that is a JSON object.

    A line being written right now, or not JSON at all, is skipped but still counts, so the
    numbers keep matching the lines of a ``.times`` file beside it.
    """
    rows: list[tuple[int, dict[str, Any]]] = []
    for number, line in enumerate(read_lines(path)):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append((number, value))
    return rows
