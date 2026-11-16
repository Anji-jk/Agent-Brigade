"""Read the Tester's and the Reviewer's answers. Ported from Agent Lab (execution/agents.py).

An answer is a claim, so it is read strictly: one JSON object, every field the right type, and
every acceptance criterion accounted for. An answer that is not like that is unusable, and
nothing is guessed from it. Pure: no I/O.
"""

import json
from dataclasses import dataclass, field
from typing import Any

MAX_TEXT_FIELD = 600
MAX_LIST_ITEMS = 40


class ReportError(ValueError):
    """An agent's final message was not the JSON report it was asked for."""


@dataclass(frozen=True, slots=True)
class TesterReport:
    summary: str
    coverage: dict[int, list[str]]  # criterion number -> the tests that cover it
    uncovered: dict[int, str]  # criterion number -> why no test covers it
    suspected_defects: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReviewerReport:
    verdict: str  # "pass" or "fail"
    met: dict[int, bool]
    evidence: dict[int, str]
    problems: list[str]  # blocking
    notes: list[str] = field(default_factory=list)  # recorded, never fail


def extract_json(text: object) -> dict[str, Any]:
    """The last top-level JSON object in `text` (code fences and prose around it are fine)."""
    if not isinstance(text, str) or not text.strip():
        raise ReportError("The agent returned no text.")
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            found = value
        index = end
    if found is None:
        raise ReportError("No JSON report found in the agent's reply.")
    return found


def _text(value: Any, name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ReportError(f"{name} must be text.")
    return value[:MAX_TEXT_FIELD]


def _text_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReportError(f"{name} must be a list of text.")
    return [item[:MAX_TEXT_FIELD] for item in value[:MAX_LIST_ITEMS]]


def _number(value: Any, count: int, name: str) -> int:
    """A 1-based criterion number inside 1..count."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= count:
        raise ReportError(f"{name} must be a criterion number from 1 to {count}.")
    return value


def _entries(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items = data.get(key) or []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ReportError(f"Each {key} entry must be an object.")
    return items


def parse_tester(text: object, criteria_count: int) -> TesterReport:
    """The Tester's JSON: which tests cover which criterion, and why some have none."""
    data = extract_json(text)
    coverage: dict[int, list[str]] = {}
    for item in _entries(data, "coverage"):
        number = _number(item.get("criterion"), criteria_count, "coverage criterion")
        coverage.setdefault(number, []).extend(_text_list(item.get("tests"), "tests"))
    uncovered = {
        _number(item.get("criterion"), criteria_count, "uncovered criterion"): _text(
            item.get("reason"), "reason"
        )
        for item in _entries(data, "uncovered")
    }
    return TesterReport(
        summary=_text(data.get("summary"), "summary"),
        coverage=coverage,
        uncovered=uncovered,
        suspected_defects=_text_list(data.get("suspected_defects"), "suspected_defects"),
        notes=_text_list(data.get("notes"), "notes"),
    )


def parse_reviewer(text: object, criteria_count: int) -> ReviewerReport:
    """The Reviewer's JSON. Every criterion must be judged exactly once, or it is unusable."""
    data = extract_json(text)
    verdict = data.get("verdict")
    if verdict not in ("pass", "fail"):
        raise ReportError('verdict must be "pass" or "fail".')
    met: dict[int, bool] = {}
    evidence: dict[int, str] = {}
    for item in _entries(data, "criteria"):
        number = _number(item.get("criterion"), criteria_count, "criterion")
        if not isinstance(item.get("met"), bool):
            raise ReportError("met must be true or false.")
        if number in met:
            raise ReportError(f"The reviewer judged criterion {number} more than once.")
        met[number] = item["met"]
        evidence[number] = _text(item.get("evidence"), "evidence")
    # A reviewer that skips a criterion has not reviewed the task: silence is not "met".
    skipped = [n for n in range(1, criteria_count + 1) if n not in met]
    if skipped:
        raise ReportError(
            "The reviewer did not judge criteria: " + ", ".join(str(n) for n in skipped)
        )
    return ReviewerReport(
        verdict,
        met,
        evidence,
        _text_list(data.get("problems"), "problems"),
        _text_list(data.get("notes"), "notes"),
    )
