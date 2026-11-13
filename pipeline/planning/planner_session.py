"""One conversation with the Planner agent: its limits, its permissions and the fix round.

The Planner runs from the Agent-Brigade folder (where .claude/agents/planner.md is found) and
may also read the project folder, but never a .env file or the project's .agent-brigade/ folder.
An answer the checks refuse is sent back once, in the same session. If the project's Git state
changes during the run, the answer is thrown away. How many turns, dollars and seconds a run
may use comes from planner_limits.py, never from this file.
"""

import uuid
from pathlib import Path
from typing import Any

from core.trackers.models import Story
from pipeline.planning.plan_fields import PlanValidationError
from pipeline.planning.plan_file import parse_planner_answer
from pipeline.planning.planner_limits import planner_limits
from pipeline.planning.planner_prompt import fix_prompt
from pipeline.planning.project_commands import check_commands
from pipeline.planning.story_plan import merge_planner_output
from pipeline.runner.claude_runner import (
    AgentError,
    AgentReply,
    AgentRequest,
    AgentRunner,
    path_rule,
    secret_rules,
)
from pipeline.workspace.git import repository_state

REPO_ROOT = Path(__file__).resolve().parents[2]  # the Agent-Brigade folder
AGENT = "planner"
TOOLS = ("Read", "Grep", "Glob")
FIX_ROUNDS = 1  # times a refused answer is sent back
LEAST_USEFUL_USD = 0.05  # with less money than this left, another round is not started


class PlanningError(Exception):
    """Planning stopped; the message says why and is safe to show."""


def planner_request(
    prompt: str, root: Path, session_id: str, resume: bool, money: float
) -> AgentRequest:
    limits = planner_limits()
    deny = (*secret_rules(REPO_ROOT, root), path_rule("Read", root, ".agent-brigade/**"))
    return AgentRequest(
        agent=AGENT,
        prompt=prompt,
        cwd=REPO_ROOT,
        session_id=session_id,
        resume=resume,
        timeout=limits.timeout_seconds,
        tools=TOOLS,
        add_dirs=(root,),
        deny=deny,
        max_turns=limits.max_turns,
        max_budget_usd=round(money, 4),
    )


def _metrics(replies: list[AgentReply], session_id: str, money: float) -> dict[str, Any]:
    def total(name: str) -> Any:
        values = [getattr(r, name) for r in replies if getattr(r, name) is not None]
        return sum(values) if values else None

    return {
        "session_id": session_id,
        "rounds": len(replies),
        "max_turns": planner_limits().max_turns,
        "max_budget_usd": round(money, 4),
        "num_turns": total("turns"),
        "total_cost_usd": total("cost_usd"),
        "duration_seconds": (total("duration_ms") or 0) / 1000 or None,
    }


def checked_answer(
    story: Story, answer: dict[str, Any], root: Path, docs_dir: str
) -> dict[str, Any]:
    """The answer joined to Jira's fields, with the project's commands checked.

    The tasks and the commands are both checked before anything is refused, so the Planner is
    told every problem in one message and one fix round is enough.
    """
    problems: list[str] = []
    checked: dict[str, Any] = {}
    try:
        checked = merge_planner_output(story, answer, docs_dir)
    except PlanValidationError as exc:
        problems.append(str(exc))
    try:
        commands = check_commands(answer.get("commands"), root)
    except PlanValidationError as exc:
        problems.append(str(exc))
    if problems:
        raise PlanValidationError(" ".join(problems))
    return {**checked, "commands": commands}


def ask_planner(
    story: Story, runner: AgentRunner, root: Path, first_prompt: str, docs_dir: str, money: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the Planner until its answer passes the checks (one fix round). (checked, metrics)

    `money` is the most the whole conversation may spend; each round gets what is left.
    """
    session_id, prompt = str(uuid.uuid4()), first_prompt
    before = repository_state(root)
    replies: list[AgentReply] = []
    problems = ""
    for round_number in range(FIX_ROUNDS + 1):
        left = money - sum(r.cost_usd or 0.0 for r in replies)
        if left < LEAST_USEFUL_USD:
            raise PlanningError(
                f"The Planner used its ${money:.2f} spending limit before its answer passed "
                f"the checks: {problems}"
            )
        try:
            request = planner_request(prompt, root, session_id, round_number > 0, left)
            replies.append(runner.run(request))
        except AgentError as exc:
            raise PlanningError(str(exc)) from None
        if repository_state(root) != before:
            raise PlanningError(
                "The project's Git state changed while planning, so the plan was not saved. "
                "The Planner may have broken its read-only rule: look at git status."
            )
        try:
            answer = parse_planner_answer(replies[-1].text)
            return checked_answer(story, answer, root, docs_dir), _metrics(
                replies, session_id, money
            )
        except PlanValidationError as exc:
            problems = str(exc)
            prompt = fix_prompt(problems)
    raise PlanningError(f"The Planner's answer was refused twice: {problems}")
