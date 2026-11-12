import pytest

from pipeline.planning import profiles as p

GOOD = """
min_role_turns = 5

[profiles.small]
model = "sonnet"
effort = "low"
max_turns = 10
timeout_seconds = 600
max_budget_usd = 1.0

[profiles.medium]
model = "sonnet"
effort = "medium"
max_turns = 25
timeout_seconds = 1200
max_budget_usd = 3

[profiles.large]
model = "opus"
effort = "high"
max_turns = 50
timeout_seconds = 2400
max_budget_usd = 10.0

[shares.builder]
turns = 1.0
budget = 0.60

[shares.tester]
turns = 0.6
budget = 0.25

[shares.reviewer]
turns = 0.4
budget = 0.15
"""


def table(tmp_path, text=GOOD):
    path = tmp_path / "profiles.toml"
    path.write_text(text, encoding="utf-8")
    return p.load_profiles(path)


def test_the_repositorys_own_table_loads_with_every_size_and_role():
    loaded = p.load_profiles()
    assert list(loaded.sizes) == ["small", "medium", "large"]
    assert set(loaded.shares) == {"builder", "tester", "reviewer"}
    assert p.profiles() is p.profiles()  # read once


def test_a_size_becomes_its_limits(tmp_path):
    loaded = table(tmp_path)
    medium = p.profile_for("medium", loaded)
    assert medium == p.RunProfile("medium", "sonnet", "medium", 25, 1200, 3.0)
    assert medium.describe() == "sonnet, medium effort, 25 turns, 1200s, $3 budget"
    with pytest.raises(ValueError, match="Unknown complexity"):
        p.profile_for("huge", loaded)


def test_each_agent_gets_its_share_and_never_fewer_than_the_least_turns(tmp_path):
    loaded = table(tmp_path)
    small = p.profile_for("small", loaded)
    builder = p.role_settings(small, "builder", loaded)
    reviewer = p.role_settings(small, "reviewer", loaded)
    assert (builder.max_turns, builder.max_budget_usd) == (10, 0.6)
    assert (reviewer.max_turns, reviewer.max_budget_usd) == (5, 0.15)  # 0.4 x 10 = 4 -> 5
    assert reviewer.describe() == "reviewer: sonnet, low effort, 5 turns, $0.15"
    with pytest.raises(ValueError, match="Unknown role"):
        p.role_settings(small, "documenter", loaded)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("[profiles.large]", "[profiles.huge]", "profiles must be exactly"),
        ('model = "opus"', 'model = " "', "large.model must be a model alias"),
        ('effort = "high"', 'effort = "extreme"', "large.effort must be one of"),
        ("max_turns = 50", "max_turns = 50.5", "max_turns must be a positive whole number"),
        ("max_turns = 50", "max_turns = 0", "max_turns must be a positive whole number"),
        ("max_turns = 50", "max_turns = true", "max_turns must be a positive whole number"),
        ("max_budget_usd = 10.0", 'max_budget_usd = "10"', "max_budget_usd must be a positive"),
        ("min_role_turns = 5", "min_role_turns = 0", "min_role_turns must be"),
        ("[shares.reviewer]", "[shares.documenter]", "shares must be exactly"),
        ("budget = 0.15", "budget = -1", "reviewer.budget must be a positive number"),
        ("[profiles.small]", "[profiles.small", "could not be read"),
    ],
)
def test_mistakes_in_the_table_are_named(tmp_path, old, new, message):
    with pytest.raises(p.ProfileError, match=message):
        table(tmp_path, GOOD.replace(old, new))


def test_a_missing_file_is_named(tmp_path):
    with pytest.raises(p.ProfileError, match="could not be read"):
        p.load_profiles(tmp_path / "missing.toml")


def test_the_printed_table_shows_sizes_shares_and_agents(tmp_path, capsys):
    text = p.format_table(table(tmp_path))
    assert "large   opus      high         50     2400      $10" in text
    assert "each agent gets at least 5 turns" in text
    assert "    tester: opus, high effort, 30 turns, $2.50" in text
    assert p.main() == 0
    assert "small   sonnet    low" in capsys.readouterr().out


def test_main_names_a_broken_table(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(p, "PROFILES_FILE", tmp_path / "missing.toml")
    assert p.main() == 1
    assert "could not be read" in capsys.readouterr().out
