import pytest

from pipeline.checks import paths as p


@pytest.mark.parametrize(
    ("path", "places", "expected"),
    [
        ("src/a.py", ["src"], True),
        ("src/a.py", ["src/"], True),
        ("src/a.py", ["src/a.py"], True),
        ("srcs/a.py", ["src"], False),
        ("src\\a.py", ["./src"], True),
        ("anything", [""], True),
        ("a.py", [], False),
    ],
)
def test_a_file_is_under_a_listed_file_or_folder(path, places, expected):
    assert p.under(path, places) is expected


@pytest.mark.parametrize(
    ("path", "secret"),
    [
        (".env", True),
        ("frontend/.env", True),
        (".env.local", True),
        (".env.production", True),
        (".env.example", False),
        ("config/.env.sample", False),
        ("environment.py", False),
        ("docs/env.md", False),
    ],
)
def test_env_files_are_secret_but_their_templates_are_not(path, secret):
    assert p.is_secret_file(path) is secret


def test_protected_paths_are_env_files_the_agent_folders_and_an_unlisted_guide():
    changed = [".env", "a/.env.local", ".agent-brigade/runs/x.json", ".claude/settings.json",
               "CLAUDE.md", "sub/CLAUDE.md", "src/ok.py", ".env.example"]  # fmt: skip
    assert p.protected(changed, ["src/ok.py"]) == [
        ".agent-brigade/runs/x.json", ".claude/settings.json", ".env", "CLAUDE.md",
        "a/.env.local", "sub/CLAUDE.md",
    ]  # fmt: skip


def test_a_guide_the_task_lists_is_allowed_but_a_secret_never_is():
    assert p.protected(["CLAUDE.md", "sub/CLAUDE.md"], ["CLAUDE.md"]) == ["sub/CLAUDE.md"]
    assert p.protected([".env"], [".env"]) == [".env"]


def test_extra_files_are_those_outside_the_task_files():
    changed = ["src/a.py", "src/deep/b.py", "docs/x.md", "README.md"]
    assert p.extra_files(changed, ["src", "README.md"]) == ["docs/x.md"]


def test_a_task_with_no_files_has_no_extra_files():
    assert p.extra_files(["anything.py"], []) == []
