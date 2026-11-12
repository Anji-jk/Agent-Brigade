"""A fake Jira for tests: a real JiraClient whose HTTP calls are answered from a dict of issues."""

import copy
import json
import re

import httpx

from core.trackers.jira.adf import adf_to_text, text_to_adf
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
        self.comments: list[tuple[str, str]] = []  # (issue key, comment text)
        self.link_posts = 0
        self.fail_link_at: int | None = None  # the n-th link (1-based) answers 400
        self.fail_comments = False  # every comment answers 400
        self.drop_links = False  # links are accepted (201) but not kept
        self.next_number = 100
        self.issue_types = [
            {"name": "Epic", "hierarchyLevel": 1},
            {"name": "Story", "hierarchyLevel": 0},
            {"name": "Subtask", "hierarchyLevel": -1, "subtask": True},
        ]

    def add(
        self,
        key,
        kind="story",
        summary="S",
        parent=None,
        description="",
        status="To Do",
        done=False,
        labels=(),
        priority=None,
    ) -> "FakeJira":
        fields = {
            "summary": summary,
            "issuetype": {
                "name": {"sub-task": "Subtask"}.get(kind, kind.capitalize()),
                "hierarchyLevel": LEVELS[kind],
                "subtask": kind == "sub-task",
            },
            "status": {"name": status, "statusCategory": {"key": "done" if done else "new"}},
            "labels": list(labels),
            "issuelinks": [],
        }
        if parent:
            fields["parent"] = {"key": parent}
        if description:
            fields["description"] = text_to_adf(description)
        if priority:
            fields["priority"] = {"name": priority}
        self.issues[key] = {"key": key, "fields": fields}
        return self

    def block(self, blocked: str, blocker: str) -> "FakeJira":
        """A Blocks link: `blocked` is blocked by `blocker`."""
        kind = {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"}
        self.issues[blocked]["fields"]["issuelinks"].append(
            {"type": kind, "inwardIssue": {"key": blocker, "fields": {"summary": "x"}}}
        )
        self.issues[blocker]["fields"]["issuelinks"].append(
            {"type": kind, "outwardIssue": {"key": blocked, "fields": {"summary": "x"}}}
        )
        return self

    def _view(self, issue: dict) -> dict:
        """The issue as Jira returns it: the parent with its summary, the story's sub-tasks."""
        view = copy.deepcopy(issue)
        fields = view["fields"]
        parent = (fields.get("parent") or {}).get("key")
        if parent in self.issues:
            fields["parent"]["fields"] = {"summary": self.issues[parent]["fields"]["summary"]}
        fields["subtasks"] = [
            {"key": key}
            for key, other in self.issues.items()
            if (other["fields"].get("parent") or {}).get("key") == issue["key"]
            and other["fields"]["issuetype"]["hierarchyLevel"] == -1
        ]
        return view

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        payload: dict = body or {}
        if self.down:
            raise httpx.ConnectError("down", request=request)
        if request.method == "GET" and "/project/" in request.url.path:
            return httpx.Response(200, json={"key": "SMT", "issueTypes": self.issue_types})
        if request.method == "POST" and request.url.path.endswith("/issue"):
            return self._create(payload["fields"])
        if request.method == "POST" and request.url.path.endswith("/issueLink"):
            return self._link(payload)
        if request.method == "POST" and request.url.path.endswith("/comment"):
            if self.fail_comments:
                return httpx.Response(400, json={"errorMessages": ["no comment"]})
            key = request.url.path.rsplit("/", 2)[1]
            self.comments.append((key, adf_to_text(payload["body"]).strip()))
            return httpx.Response(201, json={})
        if request.method == "GET" and "/issue/" in request.url.path:
            found = self.issues.get(request.url.path.rsplit("/", 1)[1])
            if not found:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=self._view(found))
        if request.method == "POST" and request.url.path.endswith("/search/jql"):
            jql = payload["jql"]
            parent = re.search(r"parent = (\S+)", jql)
            space = re.search(r'project = "([^"]+)"', jql)
            found = [
                self._view(i)
                for i in self.issues.values()
                if (not parent or (i["fields"].get("parent") or {}).get("key") == parent[1])
                and (not space or i["key"].startswith(space[1] + "-"))
                and (
                    "issuetype = Epic" not in jql or i["fields"]["issuetype"]["hierarchyLevel"] == 1
                )
            ]
            if "ORDER BY key" in jql:
                found.sort(key=lambda i: int(i["key"].rsplit("-", 1)[1]))
            return httpx.Response(200, json={"issues": found, "isLast": True})
        return httpx.Response(404, json={})

    def _link(self, body: dict) -> httpx.Response:
        """Jira's names are the wrong way round: the blocker is the inwardIssue."""
        self.link_posts += 1
        if self.link_posts == self.fail_link_at:
            return httpx.Response(400, json={"errorMessages": ["cannot link"]})
        if not self.drop_links:
            self.block(body["outwardIssue"]["key"], body["inwardIssue"]["key"])
        return httpx.Response(201)

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
