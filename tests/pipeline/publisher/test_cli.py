import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from core.settings import Settings
from core.trackers.jira.adf import text_to_adf
from core.trackers.jira.client import JiraClient
from pipeline.publisher import cli

SITE = "https://x.atlassian.net"
AGENT_FILE = Path(__file__).resolve().parents[3] / ".claude" / "agents" / "publisher.md"


def issue(key, level=0, summary="S", parent=None, description=""):
    fields = {
        "summary": summary,
        "issuetype": {"name": "x", "hierarchyLevel": level},
        "status": {"name": "To Do"},
    }
    if parent:
        fields["parent"] = {"key": parent}
    if description:
        fields["description"] = text_to_adf(description)
    return {"key": key, "fields": fields}


def settings(key="SMT"):
    values: dict[str, Any] = {
        "_env_file": None,
        "jira_site_url": SITE,
        "jira_email": "a@b.com",
        "jira_api_token": "t",
        "jira_project_key": key,
    }
    return Settings(**values)


def runner(reply, seen):
    def factory(_settings):
        def handler(request):
            seen.append(json.loads(request.content) if request.content else None)
            return reply(request)

        return JiraClient(SITE, "a@b.com", "t", transport=httpx.MockTransport(handler))

    return factory


def ok(issues):
    return lambda _r: httpx.Response(200, json={"issues": issues, "isLast": True})


def test_epics_lists_the_space_epics():
    seen = []
    code, out = cli.run(
        ["epics"],
        settings(),
        runner(
            ok([issue("SMT-4", 1, "Training Lifecycle", description="Courses and quizzes")]), seen
        ),
    )
    assert code == 0
    assert out == {
        "ok": True,
        "space": "SMT",
        "epics": [
            {
                "key": "SMT-4",
                "kind": "epic",
                "summary": "Training Lifecycle",
                "parent": None,
                "status": "To Do",
                "description": "Courses and quizzes",
            }
        ],
    }
    assert seen[0]["jql"].startswith('project = "SMT" AND issuetype = Epic')


def test_search_is_limited_to_the_env_space_and_quotes_the_text():
    seen = []
    code, out = cli.run(
        ["search", "--text", '  quiz  "final" '],
        settings(),
        runner(ok([issue("SMT-12", 0, "Quiz builder", "SMT-4")]), seen),
    )
    assert code == 0
    assert out["text"] == 'quiz "final"'
    assert out["results"][0] == {
        "key": "SMT-12",
        "kind": "story",
        "summary": "Quiz builder",
        "parent": "SMT-4",
        "status": "To Do",
    }
    jql = seen[0]["jql"]
    assert jql == 'project = "SMT" AND text ~ "quiz \\"final\\"" ORDER BY key ASC'
    assert seen[0]["fields"] == cli.SEARCH_FIELDS and seen[0]["maxResults"] == 50


@pytest.mark.parametrize(
    "argv",
    [
        ["create"],
        ["delete", "SMT-1"],
        [],
        ["search"],
        ["epics", "--project", "OTHER"],
        ["search", "--text", "x", "--space", "OTHER"],
        ["epic"],
        ["epic", "--key", "SMT-1", "--space", "OTHER"],
    ],
)
def test_anything_else_is_refused_without_calling_jira(argv):
    seen = []
    code, out = cli.run(argv, settings(), runner(ok([]), seen))
    assert code == 2 and out["ok"] is False and out["error"].startswith("Refused")
    assert seen == []


@pytest.mark.parametrize("text", ["   ", "x" * 101])
def test_empty_or_long_search_text_is_refused(text):
    seen = []
    code, out = cli.run(["search", "--text", text], settings(), runner(ok([]), seen))
    assert code == 2 and "Refused" in out["error"] and seen == []


def test_epics_in_a_small_space_carry_a_short_description():
    long = "x" * 300
    _code, out = cli.run(
        ["epics"], settings(), runner(ok([issue("SMT-4", 1, "T", description=long)]), [])
    )
    description = out["epics"][0]["description"]
    assert len(description) == cli.SHORT_DESCRIPTION_CHARS + 1 and description.endswith("…")


def test_epics_in_a_big_space_are_titles_only():
    many = [issue(f"SMT-{n}", 1, f"E{n}", description="d") for n in range(1, 12)]
    _code, out = cli.run(["epics"], settings(), runner(ok(many), []))
    assert len(out["epics"]) == 11 and all("description" not in e for e in out["epics"])


def epic_reply(epic_issue, stories=()):
    def reply(request):
        if request.method == "GET":
            return httpx.Response(200, json=epic_issue)
        return httpx.Response(200, json={"issues": list(stories), "isLast": True})

    return reply


def test_epic_returns_its_description_and_its_stories():
    seen = []
    epic = issue("SMT-4", 1, "Training Lifecycle", description="Courses, quizzes and certificates")
    stories = [issue("SMT-25", 0, "Learning Center entry", "SMT-4")]
    code, out = cli.run(
        ["epic", "--key", " smt-4 "], settings(), runner(epic_reply(epic, stories), seen)
    )
    assert code == 0 and out["ok"] is True and out["space"] == "SMT"
    assert out["epic"] == {
        "key": "SMT-4",
        "kind": "epic",
        "summary": "Training Lifecycle",
        "parent": None,
        "status": "To Do",
        "description": "Courses, quizzes and certificates",
        "description_truncated": False,
    }
    assert out["stories"] == [
        {
            "key": "SMT-25",
            "kind": "story",
            "summary": "Learning Center entry",
            "parent": "SMT-4",
            "status": "To Do",
        }
    ]
    assert seen[1]["jql"] == 'project = "SMT" AND parent = SMT-4 ORDER BY key ASC'


def test_epic_description_is_cut_and_says_so():
    epic = issue("SMT-4", 1, "T", description="y" * 1500)
    _code, out = cli.run(["epic", "--key", "SMT-4"], settings(), runner(epic_reply(epic), []))
    shown = out["epic"]["description"]
    assert len(shown) == cli.EPIC_DESCRIPTION_CHARS + 1 and shown.endswith("…")
    assert out["epic"]["description_truncated"] is True


@pytest.mark.parametrize("key", ["OTHER-1", "SMT-4 OR project = OTHER", "SMT-", "4", "SMT-1-2"])
def test_epic_key_must_be_a_key_of_the_env_space(key):
    seen = []
    code, out = cli.run(["epic", "--key", key], settings(), runner(ok([]), seen))
    assert code == 2 and out["error"].startswith("Refused") and seen == []


def test_epic_reads_epics_only():
    story = issue("SMT-25", 0, "A story", "SMT-4")
    code, out = cli.run(["epic", "--key", "SMT-25"], settings(), runner(epic_reply(story), []))
    assert code == 2 and "not an Epic" in out["error"]


def test_epic_that_does_not_exist_is_reported():
    code, out = cli.run(
        ["epic", "--key", "SMT-99"],
        settings(),
        runner(lambda _r: httpx.Response(404, json={}), []),
    )
    assert code == 1 and "SMT-99 was not found" in out["error"]


def test_jira_error_comes_back_as_json():
    code, out = cli.run(
        ["epics"], settings(), runner(lambda _r: httpx.Response(401, text="no"), [])
    )
    assert code == 1 and out["ok"] is False and "JIRA_API_TOKEN" in out["error"]


def test_missing_space_key_is_reported():
    code, out = cli.run(["epics"], settings(key=""), runner(ok([]), []))
    assert code == 1 and "JIRA_PROJECT_KEY" in out["error"]


def test_agent_definition_names_only_this_tool():
    text = AGENT_FILE.read_text(encoding="utf-8")
    assert text.startswith("---\nname: publisher\n")
    assert "tools: Bash\n" in text
    assert "python -m pipeline.publisher.cli epics" in text
    assert "python -m pipeline.publisher.cli search --text" in text
    assert "python -m pipeline.publisher.cli epic --key" in text
    assert "```plan" in text and "Acceptance criteria:" in text


def test_agent_definition_has_its_core_sections_and_no_file_access():
    text = AGENT_FILE.read_text(encoding="utf-8")
    for heading in (
        "## Overview",
        "## Responsibilities",
        "## Choosing the Epic",
        "## Restrictions",
        "## Your tool",
    ):
        assert heading in text
    assert "tools: Bash\n" in text and "Read" not in text.split("---")[1]
    assert "No file access" in text
