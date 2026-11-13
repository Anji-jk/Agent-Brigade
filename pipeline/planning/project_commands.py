"""The project's own commands, as the Planner copied them from CLAUDE.md and the docs it links to.

Brigade has no list of commands: a project may be a web app, a command-line tool or anything
else, and only its CLAUDE.md knows how it is set up, tested and built. The Planner copies two
lists into the plan, and a person approves them with the rest of it:

  setup           what a fresh copy of the project needs before anything can run
                  (a new Git worktree holds only tracked files, so installed packages are missing)
  project_checks  the project's own tests, lint and build commands, for the project as a whole

This module checks the shape of the lists, and that every command is written in CLAUDE.md or in
a Markdown file CLAUDE.md names. That is how an invented command is refused: the Planner is sent
back the line and told to copy it as written, or to leave the list empty.

Nothing here runs a command, and nothing starts an agent.
"""

import re
from pathlib import Path, PurePosixPath
from typing import Any

from pipeline.planning.plan_fields import PlanValidationError

SETUP, CHECKS = "setup", "project_checks"
KINDS = (SETUP, CHECKS)
MAX_COMMANDS = 10
MAX_COMMAND_CHARS = 300
MAX_SOURCE_FILES = 20  # CLAUDE.md and the docs it names
MAX_SOURCE_BYTES = 200_000
_DOC_PATH = re.compile(r"[\w./\\-]+\.md\b", re.IGNORECASE)
_HIDDEN_FOLDERS = {".git", ".agent-brigade"}


def empty_commands() -> dict[str, list[str]]:
    return {kind: [] for kind in KINDS}


def _command(value: object, kind: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanValidationError(f"commands.{kind} may hold only non-empty text lines.")
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise PlanValidationError(f"commands.{kind}: one command per entry, on one line.")
    if len(text) > MAX_COMMAND_CHARS:
        raise PlanValidationError(
            f"commands.{kind}: a command may have at most {MAX_COMMAND_CHARS} characters."
        )
    return text


def check_command_lists(raw: object) -> dict[str, list[str]]:
    """The two lists, checked and cleaned. Missing (an older plan) means both are empty."""
    if raw is None:
        return empty_commands()
    if not isinstance(raw, dict):
        raise PlanValidationError("commands must be an object with setup and project_checks.")
    unknown = sorted(set(raw) - set(KINDS))
    if unknown:
        raise PlanValidationError(f"commands has unknown keys: {', '.join(unknown)}.")
    found = empty_commands()
    for kind in KINDS:
        given = raw.get(kind, [])
        if not isinstance(given, list):
            raise PlanValidationError(f"commands.{kind} must be a list.")
        if len(given) > MAX_COMMANDS:
            raise PlanValidationError(f"commands.{kind} may hold at most {MAX_COMMANDS} commands.")
        for value in given:
            text = _command(value, kind)
            if text not in found[kind]:
                found[kind].append(text)
    return found


# ---------- where the commands must be written ----------


def _read_small(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _linked_doc(root: Path, written: str) -> Path | None:
    """The file a path written in CLAUDE.md names, if it is a file inside the project."""
    relative = PurePosixPath(written.replace("\\", "/"))
    if relative.is_absolute() or _HIDDEN_FOLDERS & set(relative.parts):
        return None
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def source_texts(root: Path) -> dict[str, str]:
    """CLAUDE.md and the Markdown files it names (one level), by path. {} without a CLAUDE.md."""
    main = _read_small(root / "CLAUDE.md")
    if main is None:
        return {}
    texts = {"CLAUDE.md": main}
    for written in _DOC_PATH.findall(main):
        if len(texts) >= MAX_SOURCE_FILES:
            break
        target = _linked_doc(root, written)
        name = target.relative_to(root.resolve()).as_posix() if target else ""
        if target and name not in texts and (body := _read_small(target)) is not None:
            texts[name] = body
    return texts


def _normal(text: str) -> str:
    """Text as compared: one space between words, / for \\, no difference of capital letters."""
    return " ".join(text.replace("\\", "/").split()).casefold()


def check_provenance(commands: dict[str, list[str]], root: Path) -> list[str]:
    """One sentence for each command that is not written in CLAUDE.md or a doc it names."""
    wanted = [(kind, command) for kind in KINDS for command in commands[kind]]
    if not wanted:
        return []
    texts = source_texts(root)
    if not texts:
        return ["The project has no readable CLAUDE.md, so no command can be taken from it."]
    bodies = {name: _normal(body) for name, body in texts.items()}
    where = ", ".join(texts)
    return [
        f"commands.{kind}: {command!r} is not written in {where}. "
        "Copy each command exactly as written there, or leave the list empty."
        for kind, command in wanted
        if not any(_normal(command) in body for body in bodies.values())
    ]


def check_commands(raw: object, root: Path) -> dict[str, list[str]]:
    """The planner's commands, or a PlanValidationError naming every problem at once."""
    commands = check_command_lists(raw)
    problems = check_provenance(commands, root)
    if problems:
        raise PlanValidationError(" ".join(problems))
    return commands


def describe(commands: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """(label, lines) for each non-empty list, for showing a plan as text."""
    labels = {SETUP: "Setup", CHECKS: "Checks"}
    return [(labels[kind], list(commands.get(kind) or [])) for kind in KINDS if commands.get(kind)]
