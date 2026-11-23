import pytest

from pipeline.documenting.doc_profiles import documentation_settings
from pipeline.planning.profiles import PROFILES_FILE, ProfileError

TABLE = """
[documentation.documenter]
model = "haiku"
effort = "low"
max_turns = 30
timeout_seconds = 600
max_budget_usd = 0.5

[documentation.reviewer]
model = "sonnet"
effort = "medium"
max_turns = 20
timeout_seconds = 300
max_budget_usd = 1
"""


def table(tmp_path, text=TABLE):
    path = tmp_path / "profiles.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_real_table_gives_both_agents_sonnet_and_low_effort():
    for role in ("documenter", "reviewer"):
        settings = documentation_settings(role)
        assert settings.effort == "low" and settings.model == "sonnet"
        assert settings.max_turns > 0 and settings.max_budget_usd > 0
    assert PROFILES_FILE.is_file()


def test_each_role_reads_its_own_limits(tmp_path):
    documenter = documentation_settings("documenter", table(tmp_path))
    reviewer = documentation_settings("reviewer", table(tmp_path))
    assert (documenter.model, documenter.max_turns, documenter.max_budget_usd) == ("haiku", 30, 0.5)
    assert (reviewer.model, reviewer.effort, reviewer.max_budget_usd) == ("sonnet", "medium", 1.0)
    assert reviewer.describe() == "doc-reviewer: sonnet, medium effort, 20 turns, $1.00"


def test_an_unknown_role_is_refused(tmp_path):
    with pytest.raises(ValueError, match="Unknown documentation role"):
        documentation_settings("builder", table(tmp_path))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('model = "haiku"', 'model = " "', "documenter.model must be a model alias"),
        ('effort = "low"', 'effort = "extreme"', "documenter.effort must be one of"),
        ("max_turns = 30", "max_turns = 0", "documenter.max_turns must be a positive whole"),
        ("max_budget_usd = 0.5", "max_budget_usd = true", "max_budget_usd must be a positive"),
        ("[documentation.documenter]", "[documentation.writer]", "documenter is missing"),
    ],
)
def test_mistakes_in_the_table_are_named(tmp_path, old, new, message):
    with pytest.raises(ProfileError, match=message):
        documentation_settings("documenter", table(tmp_path, TABLE.replace(old, new)))


def test_a_missing_file_or_section_is_named(tmp_path):
    with pytest.raises(ProfileError, match="could not be read"):
        documentation_settings("documenter", tmp_path / "missing.toml")
    with pytest.raises(ProfileError, match="reviewer is missing"):
        documentation_settings("reviewer", table(tmp_path, "min_role_turns = 5"))
