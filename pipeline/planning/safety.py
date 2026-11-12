"""A screen for story text that tells the agents not to do the work. Ported from Agent Lab.

Best effort and deliberately conservative: a match stops planning; no match is not a promise
that the text is safe.
"""

import re

_NEGATION = r"(?:do not|don't|dont|must not|never|should not|shall not|may not)"
_ARTICLE = r"(?:(?:a|an|any|the|new|git)\s+)*"

PROHIBITION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("forbids execution", re.compile(rf"\b{_NEGATION}\s+(?:execute|implement|start)\b", re.I)),
    (
        "forbids modifications",
        re.compile(
            rf"\b{_NEGATION}\s+(?:modify|change|edit|write to|touch)\s+"
            rf"{_ARTICLE}(?:files?|code|repo(?:sitory)?|anything)\b",
            re.I,
        ),
    ),
    ("forbids making changes", re.compile(rf"\b{_NEGATION}\s+make\s+{_ARTICLE}changes\b", re.I)),
    (
        "forbids branch creation",
        re.compile(rf"\b{_NEGATION}\s+(?:create|make|open)\s+{_ARTICLE}branch(?:es)?\b", re.I),
    ),
    (
        "forbids pull requests",
        re.compile(
            rf"\b{_NEGATION}\s+(?:create|open|submit|make|raise)\s+"
            rf"{_ARTICLE}(?:pull[- ]requests?|prs?)\b",
            re.I,
        ),
    ),
    ("forbids pull requests", re.compile(r"\bno\s+(?:pull[- ]requests?|prs?)\b", re.I)),
    (
        "marks the work as not to be done",
        re.compile(r"\b(?:read[- ]only|analysis[- ]only|plan[- ]only)\s+task\b", re.I),
    ),
)


def prohibitions(text: str) -> list[str]:
    """Why the text forbids the work, as 'reason: matched words' lines; empty when it does not."""
    found: list[str] = []
    for reason, pattern in PROHIBITION_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(f"{reason}: {match.group(0).strip()!r}")
    return found
