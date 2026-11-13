import pytest

from pipeline.planning import project_commands as pc
from pipeline.planning.plan_fields import PlanValidationError

CLAUDE = """## Commands
Install: `npm ci`
Tests: `.venv\\Scripts\\python.exe -m pytest -q`
Lint and build: see docs/commands.md and [more](docs/more.md).
"""
DOCS = "Run `cd frontend && npx eslint .` and then `npm run build`."


def project(tmp_path, claude=CLAUDE):
    (tmp_path / "docs").mkdir(exist_ok=True)
    if claude is not None:
        (tmp_path / "CLAUDE.md").write_text(claude, encoding="utf-8")
    (tmp_path / "docs" / "commands.md").write_text(DOCS, encoding="utf-8")
    (tmp_path / "docs" / "more.md").write_text("Also see docs/deeper.md.", encoding="utf-8")
    (tmp_path / "docs" / "deeper.md").write_text("Run `make secret`.", encoding="utf-8")
    return tmp_path


# ---------- the shape of the two lists ----------


def test_missing_commands_mean_two_empty_lists():
    assert pc.check_command_lists(None) == {"setup": [], "project_checks": []}
    assert pc.check_command_lists({}) == {"setup": [], "project_checks": []}


def test_commands_are_trimmed_and_listed_once():
    found = pc.check_command_lists(
        {"setup": [" npm ci ", "npm ci"], "project_checks": ["npm run build"]}
    )
    assert found == {"setup": ["npm ci"], "project_checks": ["npm run build"]}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("npm ci", "must be an object"),
        ({"setup": [], "tests": []}, "unknown keys: tests"),
        ({"setup": "npm ci"}, "commands.setup must be a list"),
        ({"setup": [f"c{n}" for n in range(11)]}, "at most 10 commands"),
        ({"project_checks": [3]}, "non-empty text lines"),
        ({"project_checks": ["  "]}, "non-empty text lines"),
        ({"setup": ["npm ci\nnpm run build"]}, "one command per entry"),
        ({"setup": ["x" * 301]}, "at most 300 characters"),
    ],
)
def test_a_bad_shape_is_refused_with_the_reason(raw, message):
    with pytest.raises(PlanValidationError, match=message):
        pc.check_command_lists(raw)


# ---------- where a command may come from ----------


def test_the_sources_are_claude_md_and_the_docs_it_names_one_level_down(tmp_path):
    texts = pc.source_texts(project(tmp_path))
    assert list(texts) == ["CLAUDE.md", "docs/commands.md", "docs/more.md"]
    assert "docs/deeper.md" not in texts  # named by a doc, not by CLAUDE.md


def test_a_path_that_leaves_the_project_or_is_hidden_is_not_read(tmp_path):
    inside = tmp_path / "proj"
    inside.mkdir()
    (tmp_path / "outside.md").write_text("Run `rm -rf x`.", encoding="utf-8")
    (inside / ".agent-brigade").mkdir()
    (inside / ".agent-brigade" / "notes.md").write_text("hidden", encoding="utf-8")
    claude = "See ../outside.md and .agent-brigade/notes.md and /etc/readme.md and missing.md"
    project(inside, claude)
    assert list(pc.source_texts(inside)) == ["CLAUDE.md"]


def test_no_claude_md_means_no_sources(tmp_path):
    assert pc.source_texts(project(tmp_path, claude=None)) == {}


# ---------- provenance ----------


def test_commands_written_in_claude_md_or_a_named_doc_are_accepted(tmp_path):
    root = project(tmp_path)
    found = pc.check_commands(
        {
            "setup": ["npm ci"],
            "project_checks": [
                ".venv\\Scripts\\python.exe -m pytest -q",
                "cd frontend && npx eslint .",
                "npm run build",
            ],
        },
        root,
    )
    assert found["setup"] == ["npm ci"] and len(found["project_checks"]) == 3


def test_spacing_capitals_and_slash_direction_do_not_matter(tmp_path):
    root = project(tmp_path)
    found = pc.check_commands(
        {"project_checks": [".venv/scripts/python.exe   -m  PYTEST -q"], "setup": []}, root
    )
    assert len(found["project_checks"]) == 1


def test_a_command_found_nowhere_is_refused_naming_it_and_where_it_looked(tmp_path):
    root = project(tmp_path)
    with pytest.raises(PlanValidationError) as caught:
        pc.check_commands(
            {"setup": ["pip install -r requirements.txt"], "project_checks": ["make secret"]},
            root,
        )
    text = str(caught.value)
    assert "commands.setup: 'pip install -r requirements.txt' is not written in CLAUDE.md," in text
    assert "docs/commands.md, docs/more.md" in text
    assert "commands.project_checks: 'make secret'" in text  # only a second-level doc has it
    assert "or leave the list empty" in text


def test_empty_lists_are_fine_even_without_a_claude_md(tmp_path):
    root = project(tmp_path, claude=None)
    assert pc.check_commands({"setup": [], "project_checks": []}, root) == {
        "setup": [],
        "project_checks": [],
    }
    assert pc.check_commands(None, root) == pc.empty_commands()


def test_a_command_with_no_claude_md_cannot_come_from_it(tmp_path):
    root = project(tmp_path, claude=None)
    with pytest.raises(PlanValidationError, match="no readable CLAUDE.md"):
        pc.check_commands({"setup": ["npm ci"]}, root)


def test_every_problem_is_reported_at_once(tmp_path):
    with pytest.raises(PlanValidationError) as caught:
        pc.check_commands({"setup": ["a b"], "project_checks": ["c d"]}, project(tmp_path))
    assert str(caught.value).count("is not written in") == 2


def test_describe_lists_only_what_is_there():
    assert pc.describe({"setup": ["npm ci"], "project_checks": []}) == [("Setup", ["npm ci"])]
    assert pc.describe({}) == []
