"""Check the Jira connection from .env, read-only:

python -m core.trackers.jira
"""

import sys

from core.settings import Settings, get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient


def check(client: JiraClient, settings: Settings) -> list[str]:
    me = client.myself()
    lines = [f"Connected to {client.site_url} as {me.get('displayName', '?')}"]
    key = settings.jira_project_key
    if not key:
        return [*lines, "JIRA_PROJECT_KEY is empty in .env: no space to read."]
    project = client.project(key)
    lines.append(f"Space {project.get('key')}: {project.get('name')}")
    epics = client.epics(key)
    lines.append(f"Epics ({len(epics)}):")
    lines += [f"  {e.key}  {e.summary}  [{e.status or '-'}]" for e in epics]
    return lines


def main() -> int:
    settings = get_settings()
    try:
        client = JiraClient.from_settings(settings)
        try:
            print("\n".join(check(client, settings)))
        finally:
            client.close()
    except TrackerError as exc:
        print(f"Jira check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
