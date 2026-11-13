"""The story checks: sub-tasks, acceptance criteria, forbidden work, blocked-by loops."""

from core.trackers.models import Story
from pipeline.planning.check_model import FAILED, OK, Check, plural
from pipeline.planning.safety import prohibitions


def _loops(story: Story) -> list[str]:
    """Open sub-tasks that are part of a cycle of blocked-by links."""
    waiting = {item.key: set(item.blocked_by) for item in story.open_subtasks()}
    for blockers in waiting.values():
        blockers.intersection_update(waiting)
    cyclic: set[str] = set()
    for start in waiting:
        pending, seen = list(waiting[start]), set()
        while pending:
            current = pending.pop()
            if current == start:
                cyclic.add(start)
                break
            if current not in seen:
                seen.add(current)
                pending.extend(waiting[current] - seen)
    return sorted(cyclic)


def check_story(story: Story) -> list[Check]:
    """The story and its sub-tasks, as Jira has them now."""
    key = story.story.key
    if not story.subtasks:
        return [Check("Story", FAILED, f"{key} has sub-tasks", "It has none: nothing to plan.")]
    found = [Check("Story", OK, f"{key} has {plural(len(story.subtasks), 'sub-task')}")]
    open_items = story.open_subtasks()
    done = [item.key for item in story.subtasks if item.done]
    if not open_items:
        detail = "Every sub-task is Done in Jira; nothing is left to do."
        return [*found, Check("Story", FAILED, "Some sub-tasks are still open", detail)]
    left_out = f"Done in Jira and left out: {', '.join(done)}" if done else ""
    found.append(Check("Story", OK, f"{len(open_items)} open", left_out))

    what = "Every open sub-task has acceptance criteria"
    missing = [item.key for item in open_items if not item.acceptance_criteria]
    found.append(
        Check(
            "Story",
            FAILED,
            what,
            f'Missing in {", ".join(missing)}. Add an "Acceptance criteria:" part to their '
            "descriptions in Jira.",
        )
        if missing
        else Check("Story", OK, what)
    )

    what = "The text does not forbid the work"
    reasons = [
        f"{item.key} {reason}"
        for item in (story.story, *open_items)
        for reason in prohibitions(f"{item.summary}\n{item.description}")
    ]
    found.append(
        Check("Story", FAILED, what, "; ".join(reasons)) if reasons else Check("Story", OK, what)
    )

    what = "Jira's blocked-by links do not loop"
    looping = _loops(story)
    links = sum(len(item.blocked_by) for item in open_items)
    if looping:
        found.append(
            Check("Story", FAILED, what, f"These wait for each other: {', '.join(looping)}.")
        )
    else:
        detail = (
            f"{plural(links, 'link')} between the sub-tasks"
            if links
            else "no links; the planner finds the order from the descriptions"
        )
        found.append(Check("Story", OK, what, detail))
    return found
