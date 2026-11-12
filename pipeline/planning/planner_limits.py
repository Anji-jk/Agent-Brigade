"""How far one planning run may go: turns, money and time.

The numbers are the ``[planner]`` table of ``profiles.toml`` beside this file, so a bigger story
needs a changed number in a table a person reads, not a change in code. Every planning and
re-planning run uses them; a story budget set at Plan can only lower the money limit.
"""

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pipeline.planning.profiles import PROFILES_FILE, ProfileError


@dataclass(frozen=True, slots=True)
class PlannerLimits:
    max_turns: int
    max_budget_usd: float
    timeout_seconds: int

    def money_for(self, story_budget: float | None) -> float:
        """The most one run may spend: the table's limit, or the story budget if that is lower."""
        if story_budget is None:
            return self.max_budget_usd
        return min(self.max_budget_usd, story_budget)


def _positive(table: dict, key: str, path: Path, *, whole: bool) -> int | float:
    value = table.get(key)
    kinds = int if whole else (int, float)
    if not isinstance(value, kinds) or isinstance(value, bool) or value <= 0:
        kind = "whole " if whole else ""
        raise ProfileError(f"{path.name}: planner.{key} must be a positive {kind}number.")
    return value


def load_planner_limits(path: Path = PROFILES_FILE) -> PlannerLimits:
    """Read and check the [planner] table. Any mistake is a ProfileError naming it."""
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ProfileError(f"{path.name} could not be read: {exc}") from None
    table = data.get("planner")
    if not isinstance(table, dict):
        raise ProfileError(
            f"{path.name}: add a [planner] table with max_turns, max_budget_usd and "
            "timeout_seconds."
        )
    return PlannerLimits(
        max_turns=int(_positive(table, "max_turns", path, whole=True)),
        max_budget_usd=float(_positive(table, "max_budget_usd", path, whole=False)),
        timeout_seconds=int(_positive(table, "timeout_seconds", path, whole=True)),
    )


@cache
def planner_limits() -> PlannerLimits:
    """The limits from profiles.toml, read once on first use."""
    return load_planner_limits()
