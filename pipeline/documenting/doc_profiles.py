"""What the Documenter and the Documentation Reviewer may use: the [documentation] table.

They are not sized by the planner (a documentation task has no Builder), so each has one fixed
set of limits in profiles.toml, beside the sizes. A mistake in the table is a ProfileError that
names it, like every other mistake in that file.
"""

import tomllib
from pathlib import Path

from pipeline.planning.profiles import EFFORTS, PROFILES_FILE, ProfileError, RoleSettings

DOC_ROLES = ("documenter", "reviewer")


def _bad(why: str) -> ProfileError:
    return ProfileError(f"{PROFILES_FILE.name}: {why}.")


def _number(table: dict, key: str, where: str, whole: bool) -> int | float:
    value = table.get(key)
    right = int if whole else (int, float)
    if isinstance(value, right) and not isinstance(value, bool) and value > 0:
        return value
    kind = "whole number" if whole else "number"
    raise _bad(f"{where}.{key} must be a positive {kind}")


def documentation_settings(role: str, path: Path | None = None) -> RoleSettings:
    """The limits of `role` ("documenter" or "reviewer") for a documentation task."""
    if role not in DOC_ROLES:
        raise ValueError(f"Unknown documentation role: {role!r}")
    file = path or PROFILES_FILE
    try:
        data = tomllib.loads(Path(file).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ProfileError(f"{Path(file).name} could not be read: {exc}") from None
    section = data.get("documentation")
    table = section.get(role) if isinstance(section, dict) else None
    where = f"documentation.{role}"
    if not isinstance(table, dict):
        raise _bad(f"{where} is missing")
    if not isinstance(table.get("model"), str) or not table["model"].strip():
        raise _bad(f"{where}.model must be a model alias")
    if table.get("effort") not in EFFORTS:
        raise _bad(f"{where}.effort must be one of {', '.join(EFFORTS)}")
    return RoleSettings(
        role=f"doc-{role}",
        model=table["model"].strip(),
        effort=table["effort"],
        max_turns=int(_number(table, "max_turns", where, True)),
        timeout_seconds=int(_number(table, "timeout_seconds", where, True)),
        max_budget_usd=float(_number(table, "max_budget_usd", where, False)),
    )
