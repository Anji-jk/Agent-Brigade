"""What a readiness check is: one finding, and all the findings for a story."""

from dataclasses import dataclass

OK, FAILED, WARNING, SKIPPED = "ok", "failed", "warning", "skipped"
LABELS = {OK: "ok", FAILED: "FAIL", WARNING: "--", SKIPPED: "skip"}
GROUPS = ("Story", "Checkout", "Project")


@dataclass(frozen=True)
class Check:
    group: str
    status: str
    what: str
    detail: str = ""


@dataclass(frozen=True)
class StoryCheck:
    story_key: str
    checks: tuple[Check, ...]

    @property
    def failed(self) -> list[Check]:
        return [check for check in self.checks if check.status == FAILED]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.status == WARNING]

    @property
    def ready(self) -> bool:
        return not self.failed


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"
