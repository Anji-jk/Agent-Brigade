"""A plan the Publisher proposes, and the result of checking it."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PlannedSubtask:
    summary: str
    description: str
    labels: tuple[str, ...] = ()
    priority: str | None = None


@dataclass(frozen=True)
class PlannedStory:
    ref: str
    epic: str
    summary: str
    description: str
    labels: tuple[str, ...] = ()
    priority: str | None = None
    subtasks: tuple[PlannedSubtask, ...] = ()


@dataclass(frozen=True)
class Plan:
    stories: tuple[PlannedStory, ...]

    def as_dict(self) -> dict:
        return asdict(self)

    def counts(self) -> dict[str, int]:
        return {
            "stories": len(self.stories),
            "subtasks": sum(len(s.subtasks) for s in self.stories),
        }


@dataclass(frozen=True)
class PlanCheck:
    plan: Plan | None
    problems: tuple[str, ...]
    fixable: bool = True  # False when Jira could not be asked: the agent cannot fix that

    @property
    def ok(self) -> bool:
        return self.plan is not None and not self.problems
