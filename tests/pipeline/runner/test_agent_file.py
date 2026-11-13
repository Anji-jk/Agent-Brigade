import pytest

from pipeline.runner import agent_file as a

TEXT = (
    "---\nname: builder\ndescription: Builds one thing\ntools: Read, Edit\n---\n"
    "\n## Overview\nDo it.\n"
)


def test_header_and_body_are_split(tmp_path):
    header, body = a.split_agent_file(TEXT)
    assert header == {"name": "builder", "description": "Builds one thing", "tools": "Read, Edit"}
    assert body == "## Overview\nDo it."
    assert a.split_agent_file(TEXT.replace("\n", "\r\n")) == (header, body)


def test_the_definition_is_what_claude_code_takes(tmp_path):
    path = tmp_path / "builder.md"
    path.write_text(TEXT, encoding="utf-8")
    assert a.agent_definitions("builder", path) == {
        "builder": {"description": "Builds one thing", "prompt": "## Overview\nDo it."}
    }


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no header", "must start with"),
        ("---\nname: x\nbody", "no closing"),
        ("---\n---\n", "no instructions"),
    ],
)
def test_a_bad_file_is_refused(tmp_path, text, message):
    path = tmp_path / "x.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(a.AgentFileError, match=message):
        a.agent_definitions("x", path)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(a.AgentFileError, match="could not be read"):
        a.agent_definitions("x", tmp_path / "nope.md")
