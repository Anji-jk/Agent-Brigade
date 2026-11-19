"""What Brigade means by a status, and the Jira names that stand for it in this space.

The code only knows five meanings. Their names in Jira come from .env, so a space whose
"In Review" is called "Needs review" changes a setting, not the code.
"""

from dataclasses import dataclass

from core.settings import Settings

TODO, IN_PROGRESS, IN_REVIEW, DONE, ERROR = "todo", "in_progress", "in_review", "done", "error"
MEANINGS = (TODO, IN_PROGRESS, IN_REVIEW, DONE, ERROR)

LABEL_STOPPED = "brigade-stopped"
LABEL_BLOCKED = "brigade-blocked"
LABEL_ERROR = "brigade-error"
LABEL_UNMERGED = "brigade-unmerged"
LABEL_MERGED = "brigade-merged"
MANAGED_LABELS = {LABEL_STOPPED, LABEL_BLOCKED, LABEL_ERROR, LABEL_UNMERGED, LABEL_MERGED}


@dataclass(frozen=True)
class StatusNames:
    todo: str
    in_progress: str
    in_review: str
    done: str
    error: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "StatusNames":
        return cls(
            settings.jira_status_todo,
            settings.jira_status_in_progress,
            settings.jira_status_in_review,
            settings.jira_status_done,
            settings.jira_status_error,
        )

    def name(self, meaning: str) -> str:
        return getattr(self, meaning)

    def all(self) -> list[str]:
        return [self.name(meaning) for meaning in MEANINGS]

    def meaning_of(self, name: str | None) -> str | None:
        """The meaning a Jira status name has here (case does not matter), or None."""
        wanted = (name or "").strip().lower()
        return next((m for m in MEANINGS if self.name(m).lower() == wanted), None)
