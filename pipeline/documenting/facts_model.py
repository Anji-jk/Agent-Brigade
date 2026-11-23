"""What is known about a finished (or stopped) story run, as plain records.

Everything here was measured by code (database, Git, plan.json), never written by an agent. The
Documenter writes from these facts, and the Reviewer checks its claims against them.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.files.atomic import write_json_atomic
from core.runs import run_directory

FACTS_FILE = "docs/facts.json"
TAIL_CHARS = 400


@dataclass(frozen=True)
class AgentRecord:
    role: str
    model: str | None
    turns: int | None
    cost_usd: float | None
    seconds: int | None
    status: str | None
    exit_reason: str | None


@dataclass(frozen=True)
class CheckRecord:
    kind: str
    passed: bool
    tail: str
    command: str = ""  # the "$ command" of a verify check, empty for the others
    result: str = ""  # "exit 1, 2.0s" or "timed out, ..."


@dataclass(frozen=True)
class FileChange:
    path: str
    added: int | None  # None for a binary file
    deleted: int | None


@dataclass(frozen=True)
class AttemptRecord:
    number: int
    outcome: str | None
    reason: str | None
    commit: str | None
    merged: bool | None  # None: the attempt never made a commit
    merge_kind: str | None
    files: tuple[FileChange, ...] | None  # None: Git could not show the commit
    checks: tuple[CheckRecord, ...] = ()
    agents: tuple[AgentRecord, ...] = ()


@dataclass(frozen=True)
class TaskFact:
    key: str
    title: str
    status: str
    size: str | None
    depends_on: tuple[str, ...]
    criteria: tuple[str, ...]
    plan_files: tuple[str, ...]
    expected_outcome: str
    attempts: tuple[AttemptRecord, ...] = ()


@dataclass(frozen=True)
class StoryFacts:
    run_id: str
    story_key: str
    story_title: str
    status: str
    branch: str | None
    base_commit: str | None
    budget_usd: float | None
    planning_cost_usd: float
    agent_cost_usd: float
    tasks: tuple[TaskFact, ...] = field(default=())

    @property
    def total_cost_usd(self) -> float:
        return round(self.planning_cost_usd + self.agent_cost_usd, 6)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_cost_usd"] = self.total_cost_usd
        return data

    def merged_files(self) -> list[str]:
        """Every path a merged attempt changed, sorted, without repeats."""
        found = {
            change.path
            for task in self.tasks
            for attempt in task.attempts
            if attempt.merged
            for change in attempt.files or ()
        }
        return sorted(found)


def facts_path(project_root: Path, run_id: str) -> Path:
    return run_directory(project_root, run_id) / FACTS_FILE


def write_facts(project_root: Path, facts: StoryFacts) -> Path:
    """Write facts.json in the run folder (never committed: .agent-brigade is ignored)."""
    path = facts_path(project_root, facts.run_id)
    write_json_atomic(path, facts.as_dict())
    return path
