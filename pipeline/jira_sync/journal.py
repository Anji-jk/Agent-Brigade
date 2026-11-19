"""Every call made to Jira for a run, one JSON line each, in the run's folder.

It is also the memory of what was already said: a comment is written once, and a status that
Jira does not have is reported once, however often the mirror runs.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

FILE = "jira-sync.jsonl"


class Journal:
    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / FILE

    def log(
        self,
        key: str,
        action: str,
        ok: bool,
        detail: str = "",
        comment_id: str | None = None,
    ) -> None:
        line = {
            "at": datetime.now(UTC).isoformat(),
            "key": key,
            "action": action,
            "ok": ok,
            "detail": detail,
        }
        if comment_id:
            line["comment_id"] = comment_id
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line) + "\n")
        except OSError:
            pass  # a log that cannot be written never stops a build

    def _lines(self) -> list[dict]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        found = []
        for raw in text.splitlines():
            try:
                found.append(json.loads(raw))
            except ValueError:
                continue  # a torn last line
        return found

    def has_comment(self, comment_id: str) -> bool:
        return any(
            line.get("comment_id") == comment_id and line.get("ok") for line in self._lines()
        )

    def has_note(self, text: str) -> bool:
        return any(
            line.get("action") == "note" and line.get("detail") == text for line in self._lines()
        )
