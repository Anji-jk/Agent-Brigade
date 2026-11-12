import pytest

from pipeline.planning.safety import prohibitions


@pytest.mark.parametrize(
    "text, reason",
    [
        ("Do not implement this yet.", "forbids execution"),
        ("Please don't modify any files.", "forbids modifications"),
        ("You must not make changes.", "forbids making changes"),
        ("Never create a new branch.", "forbids branch creation"),
        ("Do not open a pull request.", "forbids pull requests"),
        ("No PRs please.", "forbids pull requests"),
        ("This is a read-only task.", "marks the work as not to be done"),
    ],
)
def test_forbidding_text_is_found(text, reason):
    found = prohibitions(text)
    assert found and found[0].startswith(reason + ": ")


@pytest.mark.parametrize(
    "text",
    [
        "Add an export command and its tests.",
        "Do not show the salary to other employees.",
        "The page must not crash when the list is empty.",
        "",
    ],
)
def test_ordinary_text_passes(text):
    assert prohibitions(text) == []
