"""Make Jira show what wanted_for() says: correct only the difference, never stop a build.

Each step of each issue stands alone: a failed comment does not stop the status move after
it, and a failure is logged and returned as text. The next run catches the board up.
"""

from collections.abc import Callable

from core.trackers.jira.client import JiraClient, JiraError
from core.trackers.jira.moves import move_to
from core.trackers.jira.names import MANAGED_LABELS, TODO, StatusNames
from pipeline.jira_sync.journal import Journal
from pipeline.jira_sync.wanted import Wanted


class _Mirror:
    def __init__(self, client: JiraClient, names: StatusNames, journal: Journal) -> None:
        self.client, self.names, self.journal = client, names, journal
        self.problems: list[str] = []

    def step(
        self, key: str, action: str, call: Callable[[], object], detail: str, cid: str | None = None
    ) -> bool:
        try:
            call()
        except JiraError as exc:
            self.journal.log(key, action, False, f"{detail}: {exc}", cid)
            self.problems.append(f"{key}: {exc}")
            return False
        self.journal.log(key, action, True, detail, cid)
        return True

    def missing(self, space: str) -> set[str] | None:
        """Configured names Jira does not have (lower case); None: Jira cannot be reached."""
        try:
            known = {n.lower() for n in self.client.status_names(space)}
        except JiraError as exc:
            if exc.status is not None:
                return set()  # the list is not available: try each move and see
            self.journal.log(space, "status-names", False, str(exc))
            self.problems.append(str(exc))
            return None
        return {n.lower() for n in self.names.all()} - known if known else set()

    def move(self, key: str, current: str, w: Wanted, gone: set[str], space: str) -> None:
        target = self.names.name(w.status)
        if target.lower() == current.lower():
            return
        if target.lower() in gone:
            said = (
                f"Jira space {space} has no status named '{target}', so {key} cannot move there. "
                f"Statuses are named in .env (JIRA_STATUS_*): {', '.join(self.names.all())}."
            )
            if not self.journal.has_note(said):
                self.journal.log(key, "note", False, said)
                self.problems.append(said)
            return
        via = self.names.in_progress
        self.step(
            key,
            "status",
            lambda: move_to(self.client, key, target, via=via, current=current),
            f"{current} -> {target}",
        )

    def labels(self, key: str, have: set[str], w: Wanted) -> None:
        add = [name for name in w.labels if name not in have]
        remove = sorted(name for name in have & MANAGED_LABELS if name not in w.labels)
        if add or remove:
            self.step(
                key,
                "labels",
                lambda: self.client.edit_labels(key, add, remove),
                f"add {add} remove {remove}",
            )

    def comments(self, key: str, w: Wanted) -> None:
        for cid, text in w.comments:
            if not self.journal.has_comment(cid):
                self.step(key, "comment", lambda t=text: self.client.add_comment(key, t), text, cid)

    def issue(self, key: str, w: Wanted, gone: set[str], space: str) -> None:
        try:
            raw = self.client.issue_raw(key, ["status", "labels"])
        except JiraError as exc:
            self.journal.log(key, "read", False, str(exc))
            self.problems.append(f"{key}: {exc}")
            return
        if raw is None:
            self.journal.log(key, "read", False, "not found")
            self.problems.append(f"{key} was not found in Jira, so it was left alone.")
            return
        fields = raw.get("fields") or {}
        current = str((fields.get("status") or {}).get("name") or "")
        if not (w.only_from_todo and self.names.meaning_of(current) != TODO):
            self.move(key, current, w, gone, space)
        self.labels(key, set(fields.get("labels") or []), w)
        self.comments(key, w)


def mirror(
    client: JiraClient, names: StatusNames, space: str, wanted: dict[str, Wanted], journal: Journal
) -> list[str]:
    """Correct Jira to `wanted` (keys in order). Returns what could not be done, as text."""
    run = _Mirror(client, names, journal)
    gone = run.missing(space)
    if gone is None:
        return run.problems
    for key, w in wanted.items():
        run.issue(key, w, gone, space)
    return run.problems
