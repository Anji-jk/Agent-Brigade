"""Confirm: create the checked plan in Jira, then read every created item back. No database here.

    python -m pipeline.publisher.publish --session <session id>              (dry run)
    python -m pipeline.publisher.publish --session <session id> --epic SMT-7 --yes

Only a plan that passed the guard is created, and only exactly that plan: each Story under its
existing Epic, then its Sub-tasks under the new Story. Jira is checked again first, because it may
have changed since the proposal. A failure part-way stops at once; nothing is deleted, and the
result says exactly what exists. Saving the result as a publish record and telling the agent on
its next turn are the backend service's job (step 2.7); `created_note` gives the text for that.
"""

import argparse
import sys
from dataclasses import dataclass, field, replace

from core.settings import get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from pipeline.publisher.guard import Plan, check_against_jira, parse_plan

NOTE_START = "[Brigade system note: created in Jira after Confirm]"
NOTE_END = "[End of note]"


@dataclass(frozen=True)
class Created:
    kind: str  # "story" or "sub-task"
    key: str
    summary: str
    parent: str


@dataclass
class PublishResult:
    created: list[Created] = field(default_factory=list)
    error: str | None = None  # why creation stopped part-way (or never started)
    mismatches: list[str] = field(default_factory=list)  # read back differently than planned

    @property
    def ok(self) -> bool:
        return self.error is None and not self.mismatches

    @property
    def keys(self) -> list[str]:
        return [c.key for c in self.created]


def work_types(client: JiraClient, space: str) -> tuple[str, str]:
    """The names this space uses for Story and Sub-task (sites differ: 'Subtask', 'Sub-task')."""
    types = client.project(space).get("issueTypes") or []
    story = next((t["name"] for t in types if t.get("name") == "Story"), None)
    subtask = next(
        (t["name"] for t in types if t.get("hierarchyLevel") == -1 or t.get("subtask") is True),
        None,
    )
    if not story or not subtask:
        raise TrackerError(f"Space {space} has no Story or no Sub-task work type.")
    return story, subtask


def publish(plan: Plan, client: JiraClient, space: str) -> PublishResult:
    result = PublishResult()
    try:
        problems = check_against_jira(plan, client, space)
        if problems:
            result.error = "Nothing was created. " + " ".join(problems)
            return result
        story_type, subtask_type = work_types(client, space)
    except TrackerError as exc:
        result.error = f"Nothing was created. {exc}"
        return result

    for story in plan.stories:
        if not _create(client, space, story_type, story, story.epic, "story", result):
            return result
        story_key = result.created[-1].key
        for subtask in story.subtasks:
            if not _create(client, space, subtask_type, subtask, story_key, "sub-task", result):
                return result

    result.mismatches = verify(client, result.created)
    return result


def _create(client, space, issue_type, item, parent, kind, result: PublishResult) -> bool:
    try:
        key = client.create_issue(
            space,
            issue_type,
            item.summary,
            item.description,
            parent=parent,
            labels=list(item.labels),
            priority=item.priority,
        )
    except TrackerError as exc:
        made = ", ".join(result.keys) or "nothing"
        result.error = (
            f"Stopped while creating {kind} '{item.summary}' under {parent}: {exc} "
            f"Created before the stop: {made}. Nothing was deleted. If Jira timed out, check "
            f"{parent} for '{item.summary}': Jira may have created it before failing."
        )
        return False
    result.created.append(Created(kind, key, item.summary, parent))
    return True


def verify(client: JiraClient, created: list[Created]) -> list[str]:
    """Every created item read back from Jira: it exists, has the planned type and parent."""
    problems = []
    for item in created:
        try:
            found = client.issue(item.key)
        except TrackerError as exc:
            problems.append(f"{item.key} could not be read back: {exc}")
            continue
        if found is None:
            problems.append(f"{item.key} was created but cannot be found.")
        elif found.kind != item.kind:
            problems.append(f"{item.key} is a {found.kind}, planned as a {item.kind}.")
        elif found.parent_key != item.parent:
            problems.append(f"{item.key} has parent {found.parent_key}, planned {item.parent}.")
    return problems


def created_note(result: PublishResult) -> str:
    """The facts the agent gets before the user's next message, so it never creates twice."""
    lines = [NOTE_START]
    for item in result.created:
        lines.append(f"- {item.kind} {item.key} under {item.parent}: {item.summary}")
    if not result.created:
        lines.append("- nothing was created")
    if result.error:
        lines.append(f"Stopped: {result.error}")
    lines.extend(f"Check: {m}" for m in result.mismatches)
    lines.append(NOTE_END)
    return "\n".join(lines)


def _with_epic(plan: Plan, epic: str) -> Plan:
    return Plan(tuple(replace(s, epic=epic) for s in plan.stories))


def main(argv: list[str] | None = None) -> int:
    from pipeline.publisher.transcript import read_chat  # only the command needs it

    parser = argparse.ArgumentParser(prog="python -m pipeline.publisher.publish")
    parser.add_argument("--session", required=True, help="the chat's Claude session id")
    parser.add_argument("--epic", help="create under this Epic instead (for a test run)")
    parser.add_argument("--yes", action="store_true", help="really create; without it, dry run")
    args = parser.parse_args(argv)

    bubbles = read_chat(args.session)
    raw = next((b.plan for b in reversed(bubbles or []) if b.plan), None)
    if raw is None:
        print("No plan found in that chat.", file=sys.stderr)
        return 1
    parsed = parse_plan(raw)
    if parsed.plan is None or parsed.problems:
        print("The plan does not pass the guard:", *parsed.problems, sep="\n- ", file=sys.stderr)
        return 1
    plan = _with_epic(parsed.plan, args.epic.upper()) if args.epic else parsed.plan

    settings = get_settings()
    for story in plan.stories:
        print(f"Story under {story.epic}: {story.summary}")
        for subtask in story.subtasks:
            print(f"  Sub-task: {subtask.summary}")
    if not args.yes:
        print("\nDry run: nothing created. Add --yes to create these in Jira.")
        return 0

    client = JiraClient.from_settings(settings)
    try:
        result = publish(plan, client, settings.jira_project_key)
    finally:
        client.close()
    print()
    for item in result.created:
        print(f"Created {item.kind} {item.key} under {item.parent}: {client.browse_url(item.key)}")
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
    for problem in result.mismatches:
        print(f"Check: {problem}", file=sys.stderr)
    if result.ok:
        print(f"All {len(result.created)} items read back from Jira as planned.")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
