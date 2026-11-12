"""What a project gives the agents to work from: its CLAUDE.md and its docs folder.

Ported from Agent Lab (core/project_check.py). Nothing here stops planning: the planner also
gets the project's file list, so a project with less in it still plans, the planner just
searches more. The findings say what is missing, so a person can fill it in.

What helps most in CLAUDE.md (a ## or ### heading containing the word is enough, so
"Rules for the code" and "Instructions for agents" both count):

* structure     which folders the project has and what each holds
* commands      how to run the project and its tests
* rules         instructions every agent follows ("rule" and "instruction" both count)
"""

import re
from dataclasses import dataclass
from pathlib import Path

CLAUDE_FILE_NAME = "CLAUDE.md"
SECTIONS = (
    ("Project structure", ("structure",), "which folders there are and what each holds"),
    ("Commands", ("command",), "how to run the project and its tests"),
    ("Rules", ("rule", "instruction"), "instructions every agent follows"),
)
_HEADING = re.compile(r"^#{2,3}[ \t]+(.+?)[ \t#]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")


@dataclass(frozen=True)
class Finding:
    found: bool
    what: str


def section_headings(text: str) -> list[str]:
    """The ## and ### headings of a Markdown text, leaving out those inside code blocks."""
    headings: list[str] = []
    in_code = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_code = not in_code
            continue
        if not in_code:
            match = _HEADING.match(line)
            if match:
                headings.append(match.group(1).strip())
    return headings


def _claude_md(root: Path) -> tuple[str | None, Finding]:
    path = root / CLAUDE_FILE_NAME
    if not path.is_file():
        return None, Finding(
            False,
            f"no {CLAUDE_FILE_NAME}: agents get no description of the project; "
            "the planner works from the file list alone",
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return None, Finding(
            False,
            f"{CLAUDE_FILE_NAME} could not be read ({type(exc).__name__}); "
            "agents will not see it either",
        )
    return text, Finding(True, f"{CLAUDE_FILE_NAME} found")


def _sections(text: str | None) -> list[Finding]:
    if text is None:
        return []
    headings = [heading.casefold() for heading in section_headings(text)]
    return [
        Finding(True, f"{name}: {purpose}")
        if any(word in heading for heading in headings for word in words)
        else Finding(False, f"no {name} section: {purpose}")
        for name, words, purpose in SECTIONS
    ]


def _docs(root: Path, docs_dir: str) -> Finding:
    if not docs_dir:
        return Finding(
            False,
            "no docs folder (BRIGADE_DOCS_DIR in .env): the planner uses the file list, "
            "and no feature doc is written",
        )
    if (root / docs_dir).is_dir():
        return Finding(True, f"docs folder {docs_dir}/ found")
    return Finding(
        False,
        f"docs folder {docs_dir}/ (BRIGADE_DOCS_DIR in .env) does not exist yet: the planner "
        "has no docs to read, and the first feature doc makes the folder",
    )


def check_project(root: Path, docs_dir: str = "") -> list[Finding]:
    """CLAUDE.md, its three sections and the docs folder, in that order."""
    text, claude = _claude_md(root)
    return [claude, *_sections(text), _docs(root, docs_dir)]
