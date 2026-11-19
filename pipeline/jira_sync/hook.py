"""The story loop's link to Jira: after each step, make the board show where the build is.

update() never raises and never waits long: a Jira that is down, slow or refusing costs the
build nothing, and the next update catches the board up.
"""

from pathlib import Path

from sqlalchemy import Engine

from core.db import get_session
from core.db.repositories.jira_facts import cost_by_task
from core.settings import Settings
from core.trackers.jira.client import JiraClient, JiraError
from core.trackers.jira.names import StatusNames
from pipeline.jira_sync.journal import Journal
from pipeline.jira_sync.mirror import mirror
from pipeline.jira_sync.wanted import StoryFacts, TaskFacts, Wanted, wanted_for
from pipeline.stages.story_report import StoryResult


class StorySync:
    def __init__(
        self,
        client: JiraClient,
        names: StatusNames,
        run_dir: Path,
        run_id: str,
        story_key: str,
        branch: str,
        engine: Engine,
    ) -> None:
        self.client, self.names, self.run_id = client, names, run_id
        self.story_key, self.branch, self.engine = story_key, branch, engine
        self.space = story_key.rsplit("-", 1)[0]
        self.journal = Journal(run_dir)
        self.epic: str | None = None
        self.epic_looked_up = False
        self.last: dict[str, Wanted] | None = None

    def epic_key(self) -> str | None:
        """The epic above the story (the story's parent in Jira), looked up once."""
        if not self.epic_looked_up:
            try:
                raw = self.client.issue_raw(self.story_key, ["parent"]) or {}
                parent = (raw.get("fields") or {}).get("parent") or {}
                self.epic = parent.get("key") or None
                self.epic_looked_up = True
            except JiraError:
                return None  # try again at the next update
        return self.epic

    def facts(self, result: StoryResult, running: set[str], finished: bool) -> StoryFacts:
        with get_session(self.engine) as session:
            costs = cost_by_task(session, self.run_id)
        tasks = [
            TaskFacts(k, t.status, t.attempts, k in running, t.detail, costs.get(k, 0.0))
            for k, t in result.tasks.items()
        ]
        return StoryFacts(
            self.story_key, self.epic_key(), self.branch, tasks, finished, result.text()
        )

    def update(self, result: StoryResult, running: set[str], finished: bool = False) -> list[str]:
        """Correct the board; returns what could not be done, as text (the loop ignores it)."""
        try:
            wanted = wanted_for(self.facts(result, running, finished))
            if wanted == self.last:
                return []  # nothing changed since the board was last made right
            problems = mirror(self.client, self.names, self.space, wanted, self.journal)
            self.last = None if problems else wanted  # a problem is tried again next time
            return problems
        except Exception as exc:  # noqa: BLE001 - Jira trouble must never stop a build
            text = f"{type(exc).__name__}: {exc}"
            self.journal.log(self.story_key, "update", False, text)
            return [text]


def make_sync(
    settings: Settings,
    run_dir: Path,
    run_id: str,
    plan: dict,
    engine: Engine,
    client: JiraClient | None = None,
) -> StorySync | None:
    """The sync for this run, or None when it is switched off or Jira is not set up."""
    if not settings.jira_sync:
        return None
    try:
        client = client or JiraClient.from_settings(settings)
    except JiraError:
        return None
    story = str((plan.get("source") or {}).get("key") or "")
    branch = str((plan.get("config") or {}).get("branch") or "")
    if not story:
        return None
    return StorySync(
        client, StatusNames.from_settings(settings), run_dir, run_id, story, branch, engine
    )
