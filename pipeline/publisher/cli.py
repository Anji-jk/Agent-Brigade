"""The Publisher agent's only tool: read-only Jira lookups in the space named in .env.

    python -m pipeline.publisher.cli epics
    python -m pipeline.publisher.cli epic --key SMT-4
    python -m pipeline.publisher.cli search --text "training"

Prints JSON. Nothing here creates, edits or deletes: the server creates the confirmed plan
(the "Confirm and create" step). The space always comes from .env; the agent cannot choose
another one, and `epic` reads Epics of that space only.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from typing import Any

from core.settings import Settings, get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient, quote_jql
from core.trackers.models import Issue

MAX_RESULTS = 50
MAX_TEXT_CHARS = 100
SEARCH_FIELDS = ["summary", "issuetype", "parent", "status"]
SMALL_SPACE_EPICS = 10  # up to this many Epics, `epics` also shows a short description of each
SHORT_DESCRIPTION_CHARS = 200
EPIC_DESCRIPTION_CHARS = 1000
KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]+$")


class UsageError(Exception):
    """The agent asked for something this tool does not do."""


def as_json(issue: Issue) -> dict[str, Any]:
    return {
        "key": issue.key,
        "kind": issue.kind,
        "summary": issue.summary,
        "parent": issue.parent_key,
        "status": issue.status,
    }


def cut(text: str, limit: int) -> tuple[str, bool]:
    """`text` shortened to `limit` characters, and whether anything was cut."""
    text = text.strip()
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + "…", True


def epics(client: JiraClient, space: str) -> dict[str, Any]:
    found = client.epics(space, limit=MAX_RESULTS)
    small = len(found) <= SMALL_SPACE_EPICS
    items = []
    for found_epic in found:
        item = as_json(found_epic)
        if small:  # a few Epics: the agent can judge from titles plus a short description
            item["description"] = cut(found_epic.description, SHORT_DESCRIPTION_CHARS)[0]
        items.append(item)
    return {"space": space, "epics": items}


def epic(client: JiraClient, space: str, key: str) -> dict[str, Any]:
    """One Epic of the space, with its description (cut) and the Stories already under it."""
    key = key.strip().upper()
    if not KEY_PATTERN.match(key) or not key.startswith(f"{space}-"):
        raise UsageError(f"--key must be an Epic of space {space}, like {space}-1.")
    found = client.issue(key)
    if found is None:
        raise TrackerError(f"{key} was not found in space {space}.")
    if found.kind != "epic":
        raise UsageError(f"{key} is a {found.kind}, not an Epic. This command reads Epics only.")
    description, truncated = cut(found.description, EPIC_DESCRIPTION_CHARS)
    # key is checked above, so it is safe to put in the query unquoted
    jql = f"project = {quote_jql(space)} AND parent = {key} ORDER BY key ASC"
    stories = client.search(jql, MAX_RESULTS, SEARCH_FIELDS)
    return {
        "space": space,
        "epic": {
            **as_json(found),
            "description": description,
            "description_truncated": truncated,
        },
        "stories": [as_json(i) for i in stories],
    }


def search(client: JiraClient, space: str, text: str) -> dict[str, Any]:
    text = " ".join(text.split())
    if not text:
        raise UsageError("--text must not be empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise UsageError(f"--text must be at most {MAX_TEXT_CHARS} characters.")
    jql = f"project = {quote_jql(space)} AND text ~ {quote_jql(text)} ORDER BY key ASC"
    found = client.search(jql, MAX_RESULTS, SEARCH_FIELDS)
    return {"space": space, "text": text, "results": [as_json(i) for i in found]}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # raise instead of printing usage and exiting
        raise UsageError(message)


def parse(argv: list[str]) -> argparse.Namespace:
    parser = _Parser(prog="python -m pipeline.publisher.cli", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    commands.add_parser("epics", add_help=False)
    one = commands.add_parser("epic", add_help=False)
    one.add_argument("--key", required=True)
    find = commands.add_parser("search", add_help=False)
    find.add_argument("--text", required=True)
    return parser.parse_args(argv)


def run(
    argv: list[str],
    settings: Settings | None = None,
    client_factory: Callable[[Settings], JiraClient] = JiraClient.from_settings,
) -> tuple[int, dict[str, Any]]:
    """Exit code and the JSON to print: 0 ok, 1 Jira or setup problem, 2 refused."""
    try:
        args = parse(argv)
    except UsageError as exc:
        return 2, {
            "ok": False,
            "error": f"Refused: {exc} Use 'epics', 'epic --key' or 'search --text'.",
        }

    settings = settings or get_settings()
    space = settings.jira_project_key
    if not space:
        return 1, {"ok": False, "error": "JIRA_PROJECT_KEY is empty in .env."}

    try:
        client = client_factory(settings)
        try:
            if args.command == "epics":
                return 0, {"ok": True, **epics(client, space)}
            if args.command == "epic":
                return 0, {"ok": True, **epic(client, space, args.key)}
            return 0, {"ok": True, **search(client, space, args.text)}
        finally:
            client.close()
    except UsageError as exc:
        return 2, {"ok": False, "error": f"Refused: {exc}"}
    except TrackerError as exc:
        return 1, {"ok": False, "error": str(exc)}


def main() -> int:
    code, payload = run(sys.argv[1:])
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
