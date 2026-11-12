import pytest

from pipeline.planning.planner_limits import PlannerLimits, load_planner_limits, planner_limits
from pipeline.planning.profiles import ProfileError, load_profiles

GOOD = """
[planner]
max_turns = 100
max_budget_usd = 5
timeout_seconds = 1800
"""


def table(tmp_path, text):
    path = tmp_path / "profiles.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_shipped_table_has_usable_limits_and_still_loads_as_profiles():
    limits = planner_limits()
    assert limits.max_turns > 0 and limits.max_budget_usd > 0 and limits.timeout_seconds > 0
    assert load_profiles().sizes  # the new table does not disturb the sizes


def test_the_limits_are_read_from_the_planner_table(tmp_path):
    limits = load_planner_limits(table(tmp_path, GOOD))
    assert limits == PlannerLimits(max_turns=100, max_budget_usd=5.0, timeout_seconds=1800)


@pytest.mark.parametrize(
    ("budget", "expected"), [(None, 5.0), (12, 5.0), (5, 5.0), (2, 2.0), (0.5, 0.5)]
)
def test_a_story_budget_can_only_lower_the_money_limit(budget, expected):
    assert PlannerLimits(100, 5.0, 1800).money_for(budget) == expected


def test_a_missing_table_says_what_to_add(tmp_path):
    with pytest.raises(ProfileError, match=r"add a \[planner\] table"):
        load_planner_limits(table(tmp_path, "min_role_turns = 5"))


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ("max_turns = 0", "planner.max_turns must be a positive whole number"),
        ("max_turns = 2.5", "planner.max_turns must be a positive whole number"),
        ("max_turns = true", "planner.max_turns must be a positive whole number"),
        ("max_budget_usd = 'x'", "planner.max_budget_usd must be a positive number"),
        ("max_budget_usd = -1", "planner.max_budget_usd must be a positive number"),
        ("timeout_seconds = 0", "planner.timeout_seconds must be a positive whole number"),
    ],
)
def test_a_bad_value_names_the_key(tmp_path, bad, message):
    key = bad.split("=")[0].strip()
    lines = [line for line in GOOD.splitlines() if not line.startswith(key)]
    with pytest.raises(ProfileError, match=message):
        load_planner_limits(table(tmp_path, "\n".join([*lines, bad])))


def test_a_missing_or_broken_file_is_a_profile_error(tmp_path):
    with pytest.raises(ProfileError, match="could not be read"):
        load_planner_limits(tmp_path / "nothing.toml")
    with pytest.raises(ProfileError, match="could not be read"):
        load_planner_limits(table(tmp_path, "[planner"))
