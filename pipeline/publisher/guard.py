"""What the Publisher may run, and the check every proposed plan must pass before Confirm.

The agent only proposes. Its reply ends with a ```plan block (see .claude/agents/publisher.md);
this module takes that block out and checks it against the rules and against Jira. Only a plan
that passes can be confirmed, and Confirm creates exactly that plan.
"""

import json
import re
from dataclasses import asdict, dataclass

from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient, quote_jql
from pipeline.publisher.cli import KEY_PATTERN, SEARCH_FIELDS

# The only Bash commands the agent may run (Claude Code permission rules; "*" = any argument).
ALLOWED_COMMANDS = (
    "python -m pipeline.publisher.cli epics",
    "python -m pipeline.publisher.cli epic --key *",
    "python -m pipeline.publisher.cli search --text *",
)

PRIORITIES = ("Highest", "High", "Medium", "Low", "Lowest")
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,50}$")
MAX_SUMMARY_CHARS = 255
MAX_DESCRIPTION_CHARS = 20_000
MAX_STORIES = 15
MAX_SUBTASKS_PER_STORY = 20
MAX_EXISTING_STORIES = 500  # Stories read per Epic for the duplicate check
CRITERIA_LINE = "acceptance criteria:"
PLAN_BLOCK = re.compile(r"```plan[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL)


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


def find_plan_block(reply: str) -> str | None:
    """The JSON inside the last ```plan block of the reply, or None if there is none."""
    blocks = PLAN_BLOCK.findall(reply)
    return blocks[-1].strip() if blocks else None


def without_plan_block(reply: str) -> str:
    """The reply as the user reads it: the plan is drawn from the checked plan instead."""
    return PLAN_BLOCK.sub("", reply).strip()


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


class _Reader:
    """Reads one item of the plan JSON and collects what is wrong with it."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems

    def text(self, item: dict, field: str, where: str, limit: int) -> str:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            self.problems.append(f"{where}: '{field}' is missing.")
            return ""
        value = value.strip()
        if len(value) > limit:
            self.problems.append(f"{where}: '{field}' is longer than {limit} characters.")
        return value

    def summary(self, item: dict, where: str) -> str:
        value = self.text(item, "summary", where, MAX_SUMMARY_CHARS)
        if "\n" in value:
            self.problems.append(f"{where}: the summary must be one line.")
        return value

    def description(self, item: dict, where: str) -> str:
        value = self.text(item, "description", where, MAX_DESCRIPTION_CHARS)
        if value and CRITERIA_LINE not in value.casefold():
            self.problems.append(f"{where}: the description has no 'Acceptance criteria:' line.")
        return value

    def labels(self, item: dict, where: str) -> tuple[str, ...]:
        value = item.get("labels", [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            self.problems.append(f"{where}: 'labels' must be a list of words.")
            return ()
        for label in value:
            if not LABEL_PATTERN.match(label):
                self.problems.append(
                    f"{where}: label '{label}' is not one word (letters, digits, '-', '_', '.')."
                )
        return tuple(value)

    def priority(self, item: dict, where: str) -> str | None:
        value = item.get("priority")
        if value is None:
            return None
        if value not in PRIORITIES:
            self.problems.append(
                f"{where}: priority '{value}' is not one of {', '.join(PRIORITIES)}."
            )
            return None
        return value


def _subtasks(read: _Reader, story: dict, where: str) -> tuple[PlannedSubtask, ...]:
    subtasks = story.get("subtasks", [])
    if not isinstance(subtasks, list):
        read.problems.append(f"{where}: 'subtasks' must be a list.")
        return ()
    if len(subtasks) > MAX_SUBTASKS_PER_STORY:
        read.problems.append(f"{where}: more than {MAX_SUBTASKS_PER_STORY} sub-tasks.")
    planned: list[PlannedSubtask] = []
    seen: set[str] = set()
    for m, subtask in enumerate(subtasks, 1):
        sub_where = f"{where}, sub-task {m}"
        if not isinstance(subtask, dict):
            read.problems.append(f"{sub_where} is not an object.")
            continue
        summary = read.summary(subtask, sub_where)
        if summary and _norm(summary) in seen:
            read.problems.append(f"{sub_where}: '{summary}' appears twice under this story.")
        seen.add(_norm(summary))
        planned.append(
            PlannedSubtask(
                summary=summary,
                description=read.description(subtask, sub_where),
                labels=read.labels(subtask, sub_where),
                priority=read.priority(subtask, sub_where),
            )
        )
    return tuple(planned)


def _story(read: _Reader, story: dict, n: int) -> PlannedStory:
    where = f"Story {n}"
    summary = read.summary(story, where)
    if summary:
        where = f"Story {n} '{summary}'"
    epic = str(story.get("epic") or "").strip().upper()
    if not epic:
        read.problems.append(f"{where}: 'epic' is missing.")
    return PlannedStory(
        ref=str(story.get("ref") or f"S{n}"),
        epic=epic,
        summary=summary,
        description=read.description(story, where),
        labels=read.labels(story, where),
        priority=read.priority(story, where),
        subtasks=_subtasks(read, story, where),
    )


def parse_plan(raw: str) -> PlanCheck:
    """The plan JSON turned into a Plan, with every rule that does not need Jira checked."""
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return PlanCheck(None, (f"The plan block is not valid JSON: {exc}",))
    stories = data.get("stories") if isinstance(data, dict) else None
    if not isinstance(stories, list) or not stories:
        return PlanCheck(None, ("The plan has no stories.",))
    if len(stories) > MAX_STORIES:
        return PlanCheck(None, (f"The plan has more than {MAX_STORIES} stories; split it.",))

    problems: list[str] = []
    read = _Reader(problems)
    planned: list[PlannedStory] = []
    seen: set[str] = set()
    for n, story in enumerate(stories, 1):
        if not isinstance(story, dict):
            problems.append(f"Story {n} is not an object.")
            continue
        item = _story(read, story, n)
        if item.summary and _norm(item.summary) in seen:
            problems.append(f"Story {n} '{item.summary}': appears twice in the plan.")
        seen.add(_norm(item.summary))
        planned.append(item)
    return PlanCheck(Plan(tuple(planned)), tuple(problems))


def check_against_jira(plan: Plan, client: JiraClient, space: str) -> list[str]:
    """Every Epic exists in the space and is an Epic; no Story already exists under it."""
    problems: list[str] = []
    for epic in sorted({s.epic for s in plan.stories if s.epic}):
        if not KEY_PATTERN.match(epic) or not epic.startswith(f"{space}-"):
            problems.append(f"{epic} is not an Epic key of space {space}.")
            continue
        found = client.issue(epic)
        if found is None:
            problems.append(f"Epic {epic} does not exist in space {space}.")
            continue
        if found.kind != "epic":
            problems.append(f"{epic} is a {found.kind}, not an Epic.")
            continue
        jql = f"project = {quote_jql(space)} AND parent = {epic} ORDER BY key ASC"
        existing = {
            _norm(i.summary): i.key for i in client.search(jql, MAX_EXISTING_STORIES, SEARCH_FIELDS)
        }
        for story in plan.stories:
            key = existing.get(_norm(story.summary)) if story.epic == epic else None
            if key:
                problems.append(f"Story '{story.summary}' already exists under {epic} as {key}.")
    return problems


def check_plan(raw: str, client: JiraClient, space: str) -> PlanCheck:
    """The full check: shape and rules first, then Jira (only if the shape is right)."""
    parsed = parse_plan(raw)
    if parsed.plan is None or parsed.problems:
        return parsed
    try:
        problems = check_against_jira(parsed.plan, client, space)
    except TrackerError as exc:
        return PlanCheck(parsed.plan, (f"Jira could not be checked: {exc}",), fixable=False)
    return PlanCheck(parsed.plan, tuple(problems))
