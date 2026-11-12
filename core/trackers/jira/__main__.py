"""Jira from the command line, using the space in .env:

python -m core.trackers.jira              check the connection and list the epics (read-only)
python -m core.trackers.jira story KEY    read one story with its sub-tasks (read-only)
python -m core.trackers.jira sync         copy the space's board into tracker_items
"""

import argparse
import sys

from core.db import get_session, init_db, make_engine
from core.db.repositories.projects import sync_env_project
from core.settings import Settings, get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from core.trackers.jira.story import format_story, read_story
from core.trackers.jira.sync import SyncError, sync_board


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


def story(client: JiraClient, settings: Settings, key: str) -> list[str]:
    return [format_story(read_story(client, key, settings.jira_project_key or None))]


def sync(client: JiraClient, settings: Settings) -> list[str]:
    engine = init_db(make_engine(settings.db_path))
    try:
        with get_session(engine) as session:
            project = sync_env_project(session, settings)
            if project is None:
                raise SyncError("BRIGADE_PROJECT_PATH is empty in .env: no project to sync into.")
            result = sync_board(session, project.id, client, settings.jira_project_key)
    finally:
        engine.dispose()
    return [result.describe(), f"Last synced: {result.synced_at:%Y-%m-%d %H:%M} UTC"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.trackers.jira")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("check", help="check the connection and list the epics")
    read = commands.add_parser("story", help="read one story with its sub-tasks")
    read.add_argument("key")
    commands.add_parser("sync", help="copy the space's board into tracker_items")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        client = JiraClient.from_settings(settings)
        try:
            if args.command == "story":
                lines = story(client, settings, args.key)
            elif args.command == "sync":
                lines = sync(client, settings)
            else:
                lines = check(client, settings)
        finally:
            client.close()
    except TrackerError as exc:
        print(f"Jira {args.command or 'check'} failed: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
