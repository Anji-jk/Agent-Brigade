"""Catch the board up from a finished run's story report (the jira-mirror command).

For a run whose Jira calls failed while it ran (Jira was down, a status was missing and has
been fixed in .env): the report says where every task ended, and the mirror makes Jira match.
"""

import json

from sqlalchemy import Engine

from core.db import init_db
from core.runs import run_directory
from core.settings import Settings
from core.trackers.jira.client import JiraClient
from pipeline.jira_sync.hook import make_sync
from pipeline.stages.errors import BuildError
from pipeline.stages.prepare import approved_plan, project_root
from pipeline.stages.story_report import FILE, StoryResult, TaskOutcome


def catch_up(
    settings: Settings,
    run_id: str,
    engine: Engine | None = None,
    client: JiraClient | None = None,
) -> list[str]:
    """Correct Jira from the run's story report. Returns what could not be done, as text."""
    root = project_root(settings)
    plan = approved_plan(root, run_id)
    folder = run_directory(root, run_id)
    try:
        report = json.loads((folder / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(
            f"Run {run_id} has no story report: it has not run yet, or it is still running."
        ) from exc
    sync = make_sync(settings, folder, run_id, plan, init_db(engine), client)
    if sync is None:
        raise BuildError(
            "Jira is not used for this run: BRIGADE_JIRA_SYNC is off, or JIRA_SITE_URL, "
            "JIRA_EMAIL and JIRA_API_TOKEN are not set in .env."
        )
    tasks = {
        key: TaskOutcome(one["status"], int(one["attempts"]), str(one["detail"]))
        for key, one in report["tasks"].items()
    }
    return sync.update(StoryResult(run_id, tasks), set(), finished=True)
