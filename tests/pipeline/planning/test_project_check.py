from pipeline.planning.project_check import check_project, section_headings

GOOD = """# Skill Matrix

## Project structure
- backend/

### Commands
pytest

## Rules for agents
- be careful

```
## Not a heading (inside code)
```
"""


def write(tmp_path, text):
    (tmp_path / "CLAUDE.md").write_text(text, encoding="utf-8")


def test_headings_skip_code_blocks():
    assert section_headings(GOOD) == ["Project structure", "Commands", "Rules for agents"]


def test_everything_found(tmp_path):
    write(tmp_path, GOOD)
    (tmp_path / "docs").mkdir()
    findings = check_project(tmp_path, "docs")
    assert all(f.found for f in findings)
    assert [f.what.split(":")[0] for f in findings] == [
        "CLAUDE.md found",
        "Project structure",
        "Commands",
        "Rules",
        "docs folder docs/ found",
    ]


def test_instructions_heading_counts_as_rules(tmp_path):
    write(tmp_path, "## Structure\n## Commands\n## Instructions for every agent\n")
    assert all(f.found for f in check_project(tmp_path, "")[:4])


def test_missing_sections_are_named(tmp_path):
    write(tmp_path, "# Title only\n## Structure\n")
    missing = [f.what for f in check_project(tmp_path, "") if not f.found]
    assert missing[0].startswith("no Commands section")
    assert missing[1].startswith("no Rules section")
    assert "BRIGADE_DOCS_DIR" in missing[2]


def test_no_claude_md(tmp_path):
    findings = check_project(tmp_path, "docs")
    assert len(findings) == 2
    assert findings[0].what.startswith("no CLAUDE.md") and not findings[0].found
    assert "does not exist yet" in findings[1].what


def test_bom_in_claude_md_is_fine(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes("﻿## Structure\n".encode())
    assert check_project(tmp_path, "")[1].found
