import base64
import json

import httpx
import pytest

from core.settings import Settings
from core.trackers.jira.__main__ import check
from core.trackers.jira.adf import adf_to_text, text_to_adf
from core.trackers.jira.client import JiraClient, JiraError, quote_jql

SITE = "https://x.atlassian.net"
TOKEN = "topsecret-token"


def issue_json(key, level=0, name="Story", parent=None, summary="S", **fields):
    data = {
        "summary": summary,
        "issuetype": {"name": name, "hierarchyLevel": level, "subtask": level == -1},
        "status": {"name": "To Do"},
        **fields,
    }
    if parent:
        data["parent"] = {"key": parent}
    return {"key": key, "fields": data}


def make(handler, seen=None, sleeps=None):
    def wrapped(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return handler(request)

    return JiraClient(
        SITE,
        "a@b.com",
        TOKEN,
        transport=httpx.MockTransport(wrapped),
        sleep=(sleeps.append if sleeps is not None else lambda _s: None),
    )


def body(request):
    return json.loads(request.content)


# ---------- ADF ----------


def test_adf_round_trip_keeps_paragraphs_and_lines():
    text = "Acceptance criteria:\n- one\n- two\n\nSecond paragraph"
    assert adf_to_text(text_to_adf(text)).strip() == text


def test_adf_lists_code_and_mentions():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "a"}]}
                        ],
                    },
                ],
            },
            {"type": "codeBlock", "content": [{"type": "text", "text": "x = 1"}]},
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"text": "@Anji"}},
                    {"type": "unknownThing"},
                ],
            },
        ],
    }
    assert adf_to_text(doc) == "- a\n\n```\nx = 1\n```\n\n@Anji\n\n"
    assert adf_to_text(None) == "" and adf_to_text(42) == ""


# ---------- requests ----------


def test_sends_basic_auth_to_the_v3_api():
    seen = []
    make(lambda r: httpx.Response(200, json={"displayName": "Anji"}), seen).myself()
    request = seen[0]
    assert str(request.url) == f"{SITE}/rest/api/3/myself"
    expected = base64.b64encode(f"a@b.com:{TOKEN}".encode()).decode()
    assert request.headers["authorization"] == f"Basic {expected}"


def test_search_follows_pages_and_maps_issues():
    pages = [
        {"issues": [issue_json("SM-1", level=1, name="Epic")], "nextPageToken": "t2"},
        {
            "issues": [issue_json("SM-2", parent="SM-1"), issue_json("SM-3", -1, "Subtask")],
            "isLast": True,
        },
    ]
    seen = []
    issues = make(lambda r: httpx.Response(200, json=pages[len(seen) - 1]), seen).search(
        "project = SM"
    )
    assert [i.key for i in issues] == ["SM-1", "SM-2", "SM-3"]
    assert [i.kind for i in issues] == ["epic", "story", "sub-task"]
    assert issues[1].parent_key == "SM-1"
    assert body(seen[0])["jql"] == "project = SM" and "nextPageToken" not in body(seen[0])
    assert body(seen[1])["nextPageToken"] == "t2"


def test_search_stops_at_the_limit():
    page = {"issues": [issue_json(f"SM-{n}") for n in range(5)], "nextPageToken": "more"}
    seen = []
    issues = make(lambda r: httpx.Response(200, json=page), seen).search("x", limit=3)
    assert len(issues) == 3 and len(seen) == 1 and body(seen[0])["maxResults"] == 3


def test_issue_reads_description_labels_and_due_date():
    raw = issue_json(
        "SM-1",
        level=1,
        name="Epic",
        description=text_to_adf("Deliver it"),
        labels=["brigade"],
        duedate="2026-12-01",
    )
    issue = make(lambda r: httpx.Response(200, json=raw)).issue("SM-1")
    assert issue is not None
    assert issue.description == "Deliver it"
    assert issue.labels == ("brigade",) and issue.due_date == "2026-12-01"


def test_missing_issue_is_none():
    assert make(lambda r: httpx.Response(404, json={"errorMessages": ["no"]})).issue("X-9") is None


def test_epics_query_quotes_the_key():
    seen = []
    make(lambda r: httpx.Response(200, json={"issues": []}), seen).epics('S"M')
    assert body(seen[0])["jql"].startswith('project = "S\\"M" AND issuetype = Epic')


def test_create_issue_sends_fields_and_returns_the_key():
    seen = []
    client = make(lambda r: httpx.Response(201, json={"key": "SM-7"}), seen)
    key = client.create_issue(
        "SM", "Subtask", "x" * 300, "Line 1\nLine 2", parent="SM-2", labels=["qa"], priority="High"
    )
    fields = body(seen[0])["fields"]
    assert key == "SM-7"
    assert len(fields["summary"]) == 255
    assert fields["parent"] == {"key": "SM-2"} and fields["labels"] == ["qa"]
    assert fields["priority"] == {"name": "High"}
    assert fields["description"]["type"] == "doc"


def test_a_blocks_link_puts_the_blocker_in_the_inward_issue():
    seen = []
    make(lambda r: httpx.Response(201), seen).add_blocks_link("SM-12", "SM-13")
    (request,) = seen
    assert request.method == "POST" and request.url.path.endswith("/issueLink")
    assert body(request) == {
        "type": {"name": "Blocks"},
        "inwardIssue": {"key": "SM-12"},
        "outwardIssue": {"key": "SM-13"},
    }


def test_a_comment_goes_to_its_own_issue_as_rich_text():
    seen = []
    make(lambda r: httpx.Response(201, json={}), seen).add_comment("SM-13", "why\n\nbecause")
    (request,) = seen
    assert request.url.path.endswith("/issue/SM-13/comment")
    assert adf_to_text(body(request)["body"]).strip() == "why\n\nbecause"


def test_create_without_a_key_in_the_reply_fails():
    with pytest.raises(JiraError, match="did not return a key"):
        make(lambda r: httpx.Response(201, json={})).create_issue("SM", "Story", "s", "")


# ---------- errors and retries ----------


def test_unauthorised_says_what_to_check_and_hides_the_token():
    client = make(lambda r: httpx.Response(401, text="Unauthorized"))
    with pytest.raises(JiraError) as error:
        client.myself()
    assert error.value.status == 401
    assert "JIRA_API_TOKEN" in str(error.value) and TOKEN not in str(error.value)


def test_unknown_space_is_named():
    with pytest.raises(JiraError, match="space NOPE was not found"):
        make(lambda r: httpx.Response(404, json={})).project("NOPE")


def test_rate_limit_is_retried_with_retry_after():
    replies = [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json={})]
    seen, sleeps = [], []
    make(lambda r: replies[len(seen) - 1], seen, sleeps).myself()
    assert len(seen) == 2 and sleeps == [3.0]


def test_retries_stop_after_two():
    seen, sleeps = [], []
    with pytest.raises(JiraError) as error:
        make(lambda r: httpx.Response(503, text="busy"), seen, sleeps).myself()
    assert error.value.status == 503 and len(seen) == 3 and len(sleeps) == 2


def test_unreachable_site_is_a_jira_error():
    def fail(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(JiraError, match="unreachable"):
        make(fail).myself()


def test_from_settings_names_what_is_missing():
    with pytest.raises(JiraError, match="JIRA_EMAIL, JIRA_API_TOKEN"):
        JiraClient.from_settings(Settings.model_construct(jira_site_url=SITE))


def test_quote_jql():
    assert quote_jql('a"b\\c') == '"a\\"b\\\\c"'


# ---------- connection check ----------


def test_check_lists_the_space_and_its_epics():
    def handler(request):
        path = request.url.path
        if path.endswith("/myself"):
            return httpx.Response(200, json={"displayName": "Anji"})
        if path.endswith("/project/SM"):
            return httpx.Response(200, json={"key": "SM", "name": "Skill Matrix"})
        return httpx.Response(
            200, json={"issues": [issue_json("SM-1", 1, "Epic", summary="Login")], "isLast": True}
        )

    settings = Settings.model_construct(jira_project_key="SM")
    lines = check(make(handler), settings)
    assert lines == [
        f"Connected to {SITE} as Anji",
        "Space SM: Skill Matrix",
        "Epics (1):",
        "  SM-1  Login  [To Do]",
    ]
