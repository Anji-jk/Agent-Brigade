"""Small Jira Cloud REST client (API v3), basic auth with an API token.

Read: who am I, a project, issue types, search, one issue, epics of a project, and the raw
JSON of searches and issues (for readers that need fields Issue does not keep, such as links).
Write: create an issue. Nothing here deletes or edits existing work items.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

from core.settings import Settings
from core.trackers.errors import TrackerError
from core.trackers.jira.adf import text_to_adf
from core.trackers.models import Issue

FIELDS = [
    "summary",
    "description",
    "issuetype",
    "parent",
    "status",
    "labels",
    "priority",
    "duedate",
    "subtasks",
    "project",
]
MAX_SUMMARY_CHARS = 255  # Jira rejects longer summaries
PAGE_SIZE = 100  # most Jira returns per search page
RETRY_STATUSES = {429, 502, 503, 504}
MAX_RETRIES = 2
MAX_WAIT_SECONDS = 10.0


class JiraError(TrackerError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def quote_jql(value: str) -> str:
    """A JQL string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class JiraClient:
    """Tests pass an httpx.MockTransport as `transport` and a no-op `sleep`."""

    def __init__(
        self,
        site_url: str,
        email: str,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.site_url = site_url.rstrip("/")
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=f"{self.site_url}/rest/api/3",
            auth=(email, token),
            headers={"Accept": "application/json", "User-Agent": "agent-brigade"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "JiraClient":
        missing = [
            name
            for name, value in (
                ("JIRA_SITE_URL", settings.jira_site_url),
                ("JIRA_EMAIL", settings.jira_email),
                ("JIRA_API_TOKEN", settings.jira_api_token.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise JiraError(f"Jira needs {', '.join(missing)} in .env.")
        return cls(
            settings.jira_site_url,
            settings.jira_email,
            settings.jira_api_token.get_secret_value(),
        )

    def close(self) -> None:
        self._http.close()

    def browse_url(self, key: str) -> str:
        return f"{self.site_url}/browse/{key}"

    # ---------- transport ----------

    def request(self, method: str, path: str, body: dict | None = None) -> Any:
        """Send one request; retry rate limits and gateway errors; return the JSON reply."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._http.request(method, path, json=body)
            except httpx.TransportError as exc:
                raise JiraError(f"Jira is unreachable at {self.site_url}: {exc}") from exc
            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                self._sleep(_wait_seconds(response, attempt))
                continue
            if response.is_error:
                raise _error(method, path, response)
            return response.json() if response.content else None
        raise AssertionError("unreachable")  # the loop always returns or raises

    # ---------- reads ----------

    def myself(self) -> dict:
        """The account the token belongs to (proves the credentials work)."""
        return self.request("GET", "/myself")

    def project(self, key: str) -> dict:
        """The project (Jira space) with this key."""
        try:
            return self.request("GET", f"/project/{key}")
        except JiraError as exc:
            if exc.status == 404:
                raise JiraError(
                    f"Jira space {key} was not found, or this account cannot see it.", 404
                ) from exc
            raise

    def issue_type_names(self) -> set[str]:
        result = self.request("GET", "/issuetype")
        return {str(t["name"]) for t in result or [] if isinstance(t, dict) and t.get("name")}

    def search_raw(self, jql: str, fields: list[str], limit: int = 50) -> list[dict]:
        """Jira's JSON for the issues matching `jql`, in the query's order, up to `limit`."""
        found: list[dict] = []
        token: str | None = None
        while len(found) < limit:
            body: dict[str, Any] = {
                "jql": jql,
                "fields": fields,
                "maxResults": min(PAGE_SIZE, limit - len(found)),
            }
            if token:
                body["nextPageToken"] = token
            page = self.request("POST", "/search/jql", body) or {}
            found += [raw for raw in page.get("issues") or [] if isinstance(raw, dict)]
            token = page.get("nextPageToken")
            if not token or page.get("isLast", False):
                break
        return found[:limit]

    def search(self, jql: str, limit: int = 50, fields: list[str] | None = None) -> list[Issue]:
        """Issues matching `jql`, in the query's order, following pages up to `limit`."""
        return [Issue.from_jira(raw) for raw in self.search_raw(jql, fields or FIELDS, limit)]

    def issue_raw(self, key: str, fields: list[str]) -> dict | None:
        """Jira's JSON for one issue, or None if it does not exist or cannot be seen."""
        try:
            raw = self.request("GET", f"/issue/{key}?fields={','.join(fields)}")
        except JiraError as exc:
            if exc.status == 404:
                return None
            raise
        return raw if isinstance(raw, dict) and raw.get("key") else None

    def issue(self, key: str) -> Issue | None:
        """One issue, or None if it does not exist or cannot be seen."""
        raw = self.issue_raw(key, FIELDS)
        return Issue.from_jira(raw) if raw else None

    def epics(self, project: str, limit: int = 100) -> list[Issue]:
        """Epics of a project, newest first."""
        jql = f"project = {quote_jql(project)} AND issuetype = Epic ORDER BY created DESC"
        return self.search(jql, limit)

    # ---------- writes ----------

    def create_issue(
        self,
        project: str,
        issue_type: str,
        summary: str,
        description: str,
        parent: str | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
    ) -> str:
        """Create one issue (under `parent`, if given) and return its key."""
        fields: dict[str, Any] = {
            "project": {"key": project},
            "issuetype": {"name": issue_type},
            "summary": summary[:MAX_SUMMARY_CHARS],
            "description": text_to_adf(description or summary),
        }
        if parent:
            fields["parent"] = {"key": parent}
        if labels:
            fields["labels"] = labels
        if priority:
            fields["priority"] = {"name": priority}
        created = self.request("POST", "/issue", {"fields": fields})
        key = created.get("key") if isinstance(created, dict) else None
        if not key:
            raise JiraError(f"Jira did not return a key for '{summary}'.")
        return str(key)

    def add_blocks_link(self, blocker: str, blocked: str) -> None:
        """Make `blocked` "is blocked by" `blocker`.

        Jira's names are the wrong way round for this: the issue that *blocks* goes in
        ``inwardIssue``. The caller reads the link back afterwards to be sure.
        """
        self.request(
            "POST",
            "/issueLink",
            {
                "type": {"name": "Blocks"},
                "inwardIssue": {"key": blocker},
                "outwardIssue": {"key": blocked},
            },
        )

    def add_comment(self, key: str, text: str) -> None:
        """A comment on `key`. (A comment sent with a link lands on the blocker instead.)"""
        self.request("POST", f"/issue/{key}/comment", {"body": text_to_adf(text)})


def _wait_seconds(response: httpx.Response, attempt: int) -> float:
    try:
        wait = float(response.headers.get("Retry-After", ""))
    except ValueError:
        wait = 2.0**attempt
    return max(0.0, min(wait, MAX_WAIT_SECONDS))


def _error(method: str, path: str, response: httpx.Response) -> JiraError:
    status = response.status_code
    detail = " ".join(response.text.split())[:300]
    hint = {
        401: " Check JIRA_EMAIL and JIRA_API_TOKEN in .env.",
        403: " This account has no permission for that.",
    }.get(status, "")
    path = path.split("?")[0]
    return JiraError(f"Jira {method} {path} failed with {status}: {detail}{hint}", status)
