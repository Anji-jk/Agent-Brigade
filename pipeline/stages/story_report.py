"""What the story loop found, per task: the result, its text summary and its JSON report."""

from dataclasses import dataclass, field
from pathlib import Path

from core.files.atomic import write_json_atomic
from core.runs import run_directory

MERGED, FAILED, NEEDS_PERSON, BLOCKED, WAITING = (
    "merged", "failed", "needs_person", "blocked", "waiting",
)  # fmt: skip
PAUSED, CANCELLED = "stopped", "cancelled"  # a person's Stop (can continue) and Cancel (final)
WORDS = {
    MERGED: "Merged", FAILED: "Failed", NEEDS_PERSON: "Needs a person",
    BLOCKED: "Blocked", WAITING: "Not started", PAUSED: "Stopped", CANCELLED: "Cancelled",
}  # fmt: skip
NEXT = {
    FAILED: "used all its attempts: read its judge and merge reports, fix the cause (or the "
    "task), then clean and build it again",
    NEEDS_PERSON: "stopped for a person: look at its attempt, then clean and build it again",
    BLOCKED: "waits for the tasks it depends on",
    WAITING: "could not start; run story again",
    PAUSED: "stopped on request: continue it to go on from the stage it had reached",
    CANCELLED: "cancelled on request: its work is kept in Git, nothing continues it",
}
FILE = "story-report.json"


@dataclass
class TaskOutcome:
    status: str = WAITING
    attempts: int = 0
    detail: str = ""


@dataclass
class StoryResult:
    run_id: str
    tasks: dict[str, TaskOutcome] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.tasks) and all(t.status == MERGED for t in self.tasks.values())

    def statuses(self) -> dict[str, str]:
        return {key: outcome.status for key, outcome in self.tasks.items()}

    def text(self) -> str:
        merged = sum(1 for t in self.tasks.values() if t.status == MERGED)
        lines = [f"Story run {self.run_id}: {merged} of {len(self.tasks)} tasks merged."]
        for key, outcome in self.tasks.items():
            tries = f"{outcome.attempts} attempt(s)" if outcome.attempts else "no attempt"
            lines.append(f"  {key:<10} {WORDS[outcome.status]:<14} {tries}")
            if outcome.status != MERGED:
                lines.append(f"             {outcome.detail or NEXT[outcome.status]}")
        lines.append("The story is ready to review." if self.ok else "The story is not finished.")
        return "\n".join(lines)


def write_story_report(root: Path, result: StoryResult) -> Path:
    path = run_directory(root, result.run_id) / FILE
    write_json_atomic(
        path,
        {
            "run_id": result.run_id,
            "ok": result.ok,
            "tasks": {
                key: {"status": o.status, "attempts": o.attempts, "detail": o.detail}
                for key, o in result.tasks.items()
            },
        },
    )
    return path