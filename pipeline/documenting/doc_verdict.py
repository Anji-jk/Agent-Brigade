"""The Documentation Reviewer's answer, read strictly, and the pass rule that code applies to it.

Like the code Reviewer's answer it is a claim: one JSON object, every field the right type, and
every acceptance criterion judged once. Each claim it lists names the file and line, a status
(supported, unsupported or contradicted) and the evidence. Code makes the decision: a "pass"
that sits beside a claim that is not supported is a fail. Pure: no I/O.
"""

from dataclasses import dataclass, field
from typing import Any

from pipeline.checks.agent_reports import MAX_LIST_ITEMS, MAX_TEXT_FIELD, ReportError, extract_json

STATUSES = ("supported", "unsupported", "contradicted")


@dataclass(frozen=True, slots=True)
class DocClaim:
    file: str
    line: int
    claim: str
    status: str
    evidence: str


@dataclass(frozen=True, slots=True)
class DocVerdict:
    verdict: str  # "pass" or "fail", as the Reviewer said it
    claims: list[DocClaim]
    met: dict[int, bool]  # acceptance criterion number -> met
    evidence: dict[int, str]
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    passed: bool
    problems: list[str]  # what the Documenter must fix, one line each

    def feedback(self) -> str:
        return "\n".join(f"- {problem}" for problem in self.problems)


def _text(value: Any, name: str, required: bool = False) -> str:
    if value is None or value == "":
        if required:
            raise ReportError(f"{name} must not be empty.")
        return ""
    if not isinstance(value, str):
        raise ReportError(f"{name} must be text.")
    return value[:MAX_TEXT_FIELD]


def _texts(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReportError(f"{name} must be a list of text.")
    return [item[:MAX_TEXT_FIELD] for item in value[:MAX_LIST_ITEMS]]


def _objects(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items = data.get(key)
    if items is None:
        return []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ReportError(f"Each {key} entry must be an object.")
    return items


def _claim(item: dict[str, Any], lines: dict[str, int]) -> DocClaim:
    name, line = item.get("file"), item.get("line")
    if name not in lines:
        raise ReportError(f"A claim names the file {name!r}, which is not one of the documents.")
    if isinstance(line, bool) or not isinstance(line, int) or not 1 <= line <= lines[name]:
        raise ReportError(f"A claim in {name} names line {line!r}; it has {lines[name]} lines.")
    status = item.get("status")
    if status not in STATUSES:
        raise ReportError(f"A claim status must be one of {', '.join(STATUSES)}.")
    evidence = _text(item.get("evidence"), "evidence", required=True)
    return DocClaim(name, line, _text(item.get("claim"), "claim", required=True), status, evidence)


def parse_doc_review(text: object, criteria_count: int, lines: dict[str, int]) -> DocVerdict:
    """The Reviewer's JSON. `lines`: each document's name and its number of lines."""
    data = extract_json(text)
    verdict = data.get("verdict")
    if verdict not in ("pass", "fail"):
        raise ReportError('verdict must be "pass" or "fail".')
    claims = [_claim(item, lines) for item in _objects(data, "claims")]
    if any(lines.values()) and not claims:
        raise ReportError("The documents have text but the answer judges no claim in them.")
    met: dict[int, bool] = {}
    evidence: dict[int, str] = {}
    for item in _objects(data, "criteria"):
        number = item.get("criterion")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= criteria_count
        ):
            raise ReportError(f"criterion must be a number from 1 to {criteria_count}.")
        if not isinstance(item.get("met"), bool):
            raise ReportError("met must be true or false.")
        if number in met:
            raise ReportError(f"Criterion {number} was judged more than once.")
        met[number], evidence[number] = item["met"], _text(item.get("evidence"), "evidence")
    skipped = [n for n in range(1, criteria_count + 1) if n not in met]
    if skipped:
        raise ReportError("The answer did not judge criteria: " + ", ".join(map(str, skipped)))
    return DocVerdict(
        verdict, claims, met, evidence, _texts(data.get("problems"), "problems"),
        _texts(data.get("notes"), "notes"),
    )  # fmt: skip


def decide_review(verdict: DocVerdict) -> ReviewDecision:
    """Pass only when nothing is wrong: every claim has proof and every criterion is met."""
    problems: list[str] = []
    for claim in verdict.claims:
        if claim.status != "supported":
            where = f"{claim.file} line {claim.line} is {claim.status}"
            problems.append(f"{where}: {claim.claim} ({claim.evidence})")
    problems += [
        f"criterion {n} is not met: {verdict.evidence[n]}"
        for n, ok in verdict.met.items()
        if not ok
    ]
    problems += verdict.problems
    if verdict.verdict == "fail" and not problems:
        problems.append("the Reviewer failed the documents without naming a problem")
    return ReviewDecision(not problems, problems)