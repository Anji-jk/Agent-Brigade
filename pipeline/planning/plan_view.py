"""A saved plan as text, the way the Planning screen shows it before approval."""

from typing import Any

from pipeline.planning.approval import SUPERSEDED
from pipeline.planning.profiles import profile_for
from pipeline.planning.project_commands import describe
from pipeline.planning.story_plan import APPROVED


def _task_lines(task: dict[str, Any], by_id: dict[str, dict], new_links: set) -> list[str]:
    lines = [f"\n  {task['id']}  {task['jira_key']}  {task['title']}"]
    if not task["depends_on"]:
        lines.append("      Needs:   nothing")
    for blocker in task["depends_on"]:
        other = by_id[blocker]["jira_key"]
        reason = task.get("dependency_reasons", {}).get(blocker, "")
        new = (
            " [new: added to Jira after approval]" if (task["jira_key"], other) in new_links else ""
        )
        lines.append(f"      Needs:   {blocker} ({other}): {reason}{new}")
    parallel = "parallel-safe" if task["parallel_safe"] else "one at a time"
    lines.append(
        f"      Run as:  {task['complexity']}, {parallel} -> "
        f"{profile_for(task['complexity']).describe()}"
    )
    if task["files"]:
        lines.append(f"      Files:   {', '.join(task['files'])}")
    lines += [f"      Accept:  {criterion}" for criterion in task["acceptance_criteria"]]
    lines.append(f"      Outcome: {task['expected_outcome']}")
    lines += [f"      Verify:  {step}" for step in task["verification"]]
    if task.get("doc_target"):
        lines.append(f"      Doc:     {task['doc_target']}")
    context = task.get("context") or {}
    if context.get("read_first"):
        lines.append(f"      Read:    {', '.join(context['read_first'])}")
    if context.get("notes"):
        lines.append(f"      Notes:   {' '.join(context['notes'].split())}")
    return lines


def _budget_lines(record: dict[str, Any]) -> list[str]:
    """The story budget against what the tasks may spend; a warning if it cannot cover them."""
    budget = record["config"].get("budget_usd")
    total = sum(profile_for(task["complexity"]).max_budget_usd for task in record["tasks"])
    if budget is None:
        return [f"Budget:      none set (the tasks' limits add up to ${total:g})"]
    used = (record.get("planner") or {}).get("total_cost_usd") or 0
    left = budget - used
    lines = [
        f"Budget:      ${budget:g} for planning and building this story",
        f"             planning used ${used:.2f}, so ${left:.2f} is left; "
        f"the tasks' limits add up to ${total:g}",
    ]
    if total > left:
        lines.append(
            "             Warning: the task limits add up to more than what is left, so the budget "
            "may stop the build before every task has used its full limit."
        )
    return lines


def _replan_lines(record: dict[str, Any]) -> list[str]:
    replan = record["config"].get("replan")
    if not replan:
        return []
    asked = " ".join(str(replan.get("changes", "")).split())
    return [f"Re-plan of:  {replan['from_run']}", f"Changes:     {asked}"]


def _header(record: dict[str, Any]) -> list[str]:
    source, config = record["source"], record["config"]
    lines = [f"Plan for story {source['key']} - {record['issue']['title']}"]
    if source.get("epic"):
        lines.append(f"Epic:        {source['epic']['key']} {source['epic']['summary']}")
    lines += [
        f"Run ID:      {config['run_id']}",
        f"Branch:      {config['branch']} (from {config['base_ref']} at "
        f"{str(config['base_commit'])[:12]})",
        f"Model:       {config.get('model') or '(default)'}",
        *_budget_lines(record),
        *_replan_lines(record),
    ]
    if record.get("summary"):
        lines.append(f"Summary:     {record['summary']}")
    return lines + _command_lines(record)


def _command_lines(record: dict[str, Any]) -> list[str]:
    """The project's setup and check commands the plan carries (written as CLAUDE.md has them)."""
    listed = describe(record.get("commands") or {})
    if not listed:
        return ["Commands:    none listed"]
    lines = []
    for label, commands in listed:
        lines.append(f"{label + ':':<13}{commands[0]}")
        lines += [f"{'':<13}{command}" for command in commands[1:]]
    return lines


def _footer(record: dict[str, Any], path: object) -> list[str]:
    approval, planner = record.get("approval") or {}, record.get("planner") or {}
    lines = []
    if record.get("skipped_subtasks"):
        lines.append(
            "\nLeft out, done in Jira: "
            + ", ".join(f"{item['key']} ({item['status']})" for item in record["skipped_subtasks"])
        )
    if record.get("orchestrator_notes"):
        lines.append("\nWhat Brigade changed in the Planner's answer:")
        lines += [f"  - {note}" for note in record["orchestrator_notes"]]
    links = approval.get("jira_links") or []
    lines.append(f"\nJira changes after approval ({len(links)}):")
    lines += [f"  + {link['subtask']} is blocked by {link['blocked_by']}" for link in links] or [
        "  none: every dependency is already a Jira link"
    ]
    if approval.get("status") == APPROVED:
        status = f"approved {approval.get('approved_at', '')}".strip()
    elif approval.get("status") == SUPERSEDED:
        status = f"replaced by {approval.get('superseded_by')}"
    else:
        status = "waiting for approval"
    lines.append(f"Status:      {status}")
    metrics = [
        f"{label} {format(planner[key], spec)}"
        for label, key, spec in (
            ("duration s", "duration_seconds", ".1f"),
            ("cost USD", "total_cost_usd", ".4f"),
            ("turns", "num_turns", "g"),
            ("rounds", "rounds", "g"),
        )
        if isinstance(planner.get(key), (int, float))
    ]
    if metrics:
        lines.append(f"Planner:     {', '.join(metrics)}")
    lines.append(f"Plan file:   {path}")
    return lines


def format_plan(record: dict[str, Any], path: object) -> str:
    """The plan for review: header, each task in Jira's order, then what Approve would do."""
    tasks = record["tasks"]
    by_id = {task["id"]: task for task in tasks}
    links = (record.get("approval") or {}).get("jira_links") or []
    new_links = {(link["subtask"], link["blocked_by"]) for link in links}
    lines = _header(record)
    lines.append(f"\nTasks ({len(tasks)}), in Jira's order:")
    for task in tasks:
        lines += _task_lines(task, by_id, new_links)
    lines += _footer(record, path)
    return "\n".join(lines)
