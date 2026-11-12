"""How much model, effort, time and money a task of each size gets.

The planner labels each task small, medium or large. This module turns the label into
concrete limits from ``profiles.toml`` beside this file, so spending is decided by a table a
person reads and reviews like code, not by the AI. Each agent of a task (builder, tester,
reviewer) then gets a share of the task's turns and budget.

Show the table: ``python -m pipeline.planning.profiles``
"""

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pipeline.planning.plan_fields import COMPLEXITIES

PROFILES_FILE = Path(__file__).resolve().with_name("profiles.toml")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
ROLE_NAMES = ("builder", "tester", "reviewer")


@dataclass(frozen=True, slots=True)
class RunProfile:
    complexity: str
    model: str  # a Claude Code model alias
    effort: str  # one of EFFORTS
    max_turns: int
    timeout_seconds: int
    max_budget_usd: float

    def describe(self) -> str:
        return (
            f"{self.model}, {self.effort} effort, {self.max_turns} turns, "
            f"{self.timeout_seconds}s, ${self.max_budget_usd:g} budget"
        )


@dataclass(frozen=True, slots=True)
class RoleSettings:
    role: str
    model: str
    effort: str
    max_turns: int
    timeout_seconds: int
    max_budget_usd: float

    def describe(self) -> str:
        return (
            f"{self.role}: {self.model}, {self.effort} effort, "
            f"{self.max_turns} turns, ${self.max_budget_usd:.2f}"
        )


@dataclass(frozen=True, slots=True)
class Profiles:
    sizes: dict[str, RunProfile]
    min_role_turns: int  # the least turns any one agent gets
    shares: dict[str, tuple[float, float]]  # role -> (turn share, budget share)


class ProfileError(ValueError):
    """profiles.toml is missing, unreadable or breaks its rules."""


def _bad(why: str) -> ProfileError:
    return ProfileError(f"{PROFILES_FILE.name}: {why}.")


def _whole(table: dict, key: str, where: str) -> int:
    value = table.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise _bad(f"{where}.{key} must be a positive whole number")


def _positive(table: dict, key: str, where: str) -> float:
    value = table.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    raise _bad(f"{where}.{key} must be a positive number")


def _profile(name: str, table: object) -> RunProfile:
    where = f"profiles.{name}"
    if not isinstance(table, dict):
        raise _bad(f"{where} must be a table")
    if not isinstance(table.get("model"), str) or not table["model"].strip():
        raise _bad(f"{where}.model must be a model alias")
    if table.get("effort") not in EFFORTS:
        raise _bad(f"{where}.effort must be one of {', '.join(EFFORTS)}")
    return RunProfile(
        complexity=name,
        model=table["model"].strip(),
        effort=table["effort"],
        max_turns=_whole(table, "max_turns", where),
        timeout_seconds=_whole(table, "timeout_seconds", where),
        max_budget_usd=_positive(table, "max_budget_usd", where),
    )


def _shares(data: dict) -> dict[str, tuple[float, float]]:
    tables = data.get("shares") or {}
    if set(tables) != set(ROLE_NAMES):
        raise _bad(f"shares must be exactly {', '.join(ROLE_NAMES)}")
    shares = {}
    for role in ROLE_NAMES:
        where = f"shares.{role}"
        table = tables[role] if isinstance(tables[role], dict) else {}
        shares[role] = (
            _positive(table, "turns", where),
            _positive(table, "budget", where),
        )
    return shares


def load_profiles(path: Path = PROFILES_FILE) -> Profiles:
    """Read and check the table. Any mistake is a ProfileError naming it."""
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ProfileError(f"{Path(path).name} could not be read: {exc}") from None
    tables = data.get("profiles") or {}
    if set(tables) != set(COMPLEXITIES):
        raise _bad(f"profiles must be exactly {', '.join(COMPLEXITIES)}")
    minimum = data.get("min_role_turns")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        raise _bad("min_role_turns must be a positive whole number")
    return Profiles(
        sizes={name: _profile(name, tables[name]) for name in COMPLEXITIES},
        min_role_turns=minimum,
        shares=_shares(data),
    )


@cache
def profiles() -> Profiles:
    """The table from profiles.toml, read once on first use (not at import)."""
    return load_profiles()


def profile_for(complexity: str, table: Profiles | None = None) -> RunProfile:
    table = table or profiles()
    try:
        return table.sizes[complexity]
    except KeyError:
        raise ValueError(f"Unknown complexity: {complexity!r}") from None


def role_settings(profile: RunProfile, role: str, table: Profiles | None = None) -> RoleSettings:
    """What one agent of a task may use: its share of the task's profile."""
    table = table or profiles()
    try:
        turn_share, budget_share = table.shares[role]
    except KeyError:
        raise ValueError(f"Unknown role: {role!r}") from None
    return RoleSettings(
        role=role,
        model=profile.model,
        effort=profile.effort,
        max_turns=max(table.min_role_turns, round(profile.max_turns * turn_share)),
        timeout_seconds=profile.timeout_seconds,
        max_budget_usd=round(profile.max_budget_usd * budget_share, 4),
    )


def format_table(table: Profiles) -> str:
    """The sizes and each role's share, as text."""
    lines = [
        f"{'size':<8}{'model':<10}{'effort':<9}{'turns':>6}{'seconds':>9}{'budget':>9}",
    ]
    for profile in table.sizes.values():
        lines.append(
            f"{profile.complexity:<8}{profile.model:<10}{profile.effort:<9}"
            f"{profile.max_turns:>6}{profile.timeout_seconds:>9}"
            f"{'$' + format(profile.max_budget_usd, 'g'):>9}"
        )
    lines.append("")
    lines.append(f"Shares of a task (each agent gets at least {table.min_role_turns} turns):")
    for role, (turns, budget) in table.shares.items():
        lines.append(f"  {role:<9} turns {turns:g}, budget {budget:g}")
    lines.append("")
    lines.append("What each agent gets:")
    for profile in table.sizes.values():
        lines.append(f"  {profile.complexity}")
        lines += [f"    {role_settings(profile, role, table).describe()}" for role in ROLE_NAMES]
    return "\n".join(lines)


def main() -> int:
    try:
        table = load_profiles(PROFILES_FILE)
    except ProfileError as exc:
        print(exc)
        return 1
    print(f"Profiles from {PROFILES_FILE}\n")
    print(format_table(table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
