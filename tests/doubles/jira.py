"""A fake Jira for tests: a real JiraClient whose HTTP calls are answered from a dict of issues."""

import json
import re

import httpx

from core.trackers.jira.adf import text_to_adf
from core.trackers.jira.client import JiraClient

SITE = "https://x.atlassian.net"
LEVELS = {"epic": 1, "story": 0, "sub-task": -1}


class FakeJira:
    def __init__(self) -> None:
        self.issues: dict[str, dict] = {}
        self.requests: list[tuple[str, str, dict | None]] = []
        self.down = False  # True: every call fails as if Jira were unreachable
        self.fail_create_at: int | None = None  # the n-th create (1-based) answers 400
        self.creates = 0
        self.next_number = 100
        self.issue_types = [
            {"name": "Epic", "hierarchyLevel": 1},
            {"name": "Story", "hierarchyLevel": 0},
            {"name": "Subtask", "hierarchyLevel": -1, "subtask": True},
        ]

    def add(self, key, kind="story", summary="S", parent=None, description="") -> "FakeJira":
        fields = {
            "summary": summary,
            "issuetype": {"name": kind, "hierarchyLevel": LEVELS[kind]},
            "status": {"name": "To Do"},
        }
        if parent:
            fields["parent"] = {"key": parent}
        if description:
            fields["description"] = text_to_adf(description)
        self.issues[key] = {"key": key, "fields": fields}
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        if self.down:
            raise httpx.ConnectError("down", request=request)
        if request.method == "GET" and "/project/" in request.url.path:
            return httpx.Response(200, json={"key": "SMT", "issueTypes": self.issue_types})
        if request.method == "POST" and request.url.path.endswith("/issue"):
            if body is None:
                return httpx.Response(400, json={"error": "missing request body"})
            return self._create(body["fields"])
        if request.method == "GET" and "/issue/" in request.url.path:
            found = self.issues.get(request.url.path.rsplit("/", 1)[1])
            return httpx.Response(200, json=found) if found else httpx.Response(404, json={})
        if request.method == "POST" and request.url.path.endswith("/search/jql"):
            if body is None:
                return httpx.Response(400, json={"error": "missing request body"})
            jql = body["jql"]
            parent = re.search(r"parent = (\S+)", jql)
            found = [
                i
                for i in self.issues.values()
                if (not parent or (i["fields"].get("parent") or {}).get("key") == parent[1])
                and (
                    "issuetype = Epic" not in jql or i["fields"]["issuetype"]["hierarchyLevel"] == 1
                )
            ]
            return httpx.Response(200, json={"issues": found, "isLast": True})
        return httpx.Response(404, json={})

    def _create(self, fields: dict) -> httpx.Response:
        self.creates += 1
        if self.creates == self.fail_create_at:
            return httpx.Response(400, json={"errors": {"priority": "cannot be set"}})
        names = {t["name"]: t["hierarchyLevel"] for t in self.issue_types}
        level = names[fields["issuetype"]["name"]]
        kind = next(k for k, v in LEVELS.items() if v == level)
        key = f"{fields['project']['key']}-{self.next_number}"
        self.next_number += 1
        self.add(key, kind, fields["summary"], (fields.get("parent") or {}).get("key"))
        self.issues[key]["fields"]["labels"] = fields.get("labels", [])
        return httpx.Response(201, json={"key": key})

    def client(self, _settings=None) -> JiraClient:
        return JiraClient(
            SITE,
            "a@b.c",
            "t",
            transport=httpx.MockTransport(self.handler),
            sleep=lambda _seconds: None,
        )
