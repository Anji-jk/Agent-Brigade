"""The facts of a run as text for the command line."""

from pipeline.documenting.facts_model import AttemptRecord, StoryFacts


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.4f}"


def _attempt(attempt: AttemptRecord) -> list[str]:
    merged = {True: "merged", False: "not merged", None: "no commit"}[attempt.merged]
    lines = [f"    attempt {attempt.number}: {attempt.outcome or 'unfinished'}, {merged}"]
    if attempt.reason:
        lines.append(f"      reason: {attempt.reason}")
    if attempt.files is None and attempt.commit:
        lines.append(f"      commit {attempt.commit[:12]}: Git cannot show it")
    for change in attempt.files or ():
        lines.append(f"      file {change.path}  +{change.added} -{change.deleted}")
    for check in attempt.checks:
        shown = f"      check {check.kind}: {'passed' if check.passed else 'FAILED'}"
        if check.command:
            shown += f"  $ {check.command} ({check.result})"
        lines.append(shown)
    for agent in attempt.agents:
        cost = _money(agent.cost_usd)
        lines.append(f"      agent {agent.role}: {agent.status}, {agent.turns} turns, {cost}")
    return lines


def format_facts(facts: StoryFacts) -> str:
    lines = [
        f"Run {facts.run_id}  story {facts.story_key}  {facts.story_title}",
        f"Status {facts.status}  branch {facts.branch}  base {(facts.base_commit or '')[:12]}",
        f"Cost: planning {_money(facts.planning_cost_usd)} + agents {_money(facts.agent_cost_usd)}"
        f" = {_money(facts.total_cost_usd)}  (budget {_money(facts.budget_usd)})",
    ]
    for task in facts.tasks:
        lines.append(f"  {task.key}  {task.status}  {task.title}")
        for attempt in task.attempts:
            lines.extend(_attempt(attempt))
    lines.append(f"Merged files: {', '.join(facts.merged_files()) or 'none'}")
    return "\n".join(lines)
