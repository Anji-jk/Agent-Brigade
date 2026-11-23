"""Collect the facts of a story run from the database, Git and plan.json. No agent, no cost."""

from pathlib import Path

from sqlalchemy.engine import Engine

from core.db import get_session
from core.db.models import Check, StoryRun
from core.db.repositories import story_runs
from core.db.repositories.attempt_rows import checks_of
from core.db.repositories.progress_rows import AttemptRows, rows_of_run
from pipeline.documenting.facts_model import (
    TAIL_CHARS,
    AgentRecord,
    AttemptRecord,
    CheckRecord,
    FileChange,
    StoryFacts,
    TaskFact,
)
from pipeline.planning.plan_file import load_plan
from pipeline.workspace.git import GitError, run_git


class FactsError(RuntimeError):
    """The run is unknown, or its facts cannot be read."""


def _number(text: str) -> int | None:
    return None if text == "-" else int(text)


def commit_files(root: Path, sha: str) -> tuple[FileChange, ...] | None:
    """What one commit changed, from Git; None when Git cannot show it."""
    try:
        out = run_git(root, "show", "--numstat", "--format=", sha)
    except GitError:
        return None
    changes = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            changes.append(FileChange(parts[2], _number(parts[0]), _number(parts[1])))
    return tuple(changes)


def is_merged(root: Path, sha: str, branch: str | None) -> bool:
    """Whether the commit is part of the story branch: Git answers, not the database."""
    if not branch:
        return False
    try:
        run_git(root, "merge-base", "--is-ancestor", sha, branch)
    except GitError:
        return False
    return True


def _check(row) -> CheckRecord:
    """A check row; a verify row begins with its command and result, which the tail may cut."""
    text = row.output_tail or ""
    lines = text.split("\n", 2)
    command, result = (
        (lines[0][2:], lines[1]) if text.startswith("$ ") and len(lines) > 1 else ("", "")
    )
    return CheckRecord(row.kind, bool(row.passed), text[-TAIL_CHARS:], command, result)


def _attempt(
    root: Path, branch: str | None, rows: AttemptRows, checks: list[Check]
) -> AttemptRecord:
    attempt = rows.attempt
    sha = attempt.commit_sha
    return AttemptRecord(
        number=attempt.number,
        outcome=attempt.outcome,
        reason=attempt.reason,
        commit=sha,
        merged=is_merged(root, sha, branch) if sha else None,
        merge_kind=rows.merge.kind if rows.merge else None,
        files=commit_files(root, sha) if sha else None,
        checks=tuple(_check(c) for c in checks),
        agents=tuple(
            AgentRecord(
                a.role,
                a.model_used or a.model_requested,
                a.turns,
                float(a.cost) if a.cost is not None else None,
                a.duration_s,
                a.status,
                a.exit_reason,
            )
            for a in rows.agents
        ),
    )


def collect_facts(engine: Engine, project_root: Path, run_id: str) -> StoryFacts:
    """The facts of one run. Reads the database and Git; changes nothing."""
    plan = load_plan(project_root, run_id)
    tasks = {task["jira_key"]: task for task in plan["tasks"] if "jira_key" in task}
    key_of = {task["id"]: task["jira_key"] for task in plan["tasks"] if "jira_key" in task}
    with get_session(engine) as session:
        run: StoryRun | None = story_runs.run_by_id(session, run_id)
        if run is None:
            raise FactsError(f"Run {run_id} is not in the database.")
        title = plan.get("issue", {}).get("title", "")
        facts: list[TaskFact] = []
        total_agents = 0.0
        for rows in rows_of_run(session, run.id):
            key = rows.sub_task.key
            task = tasks.get(key, {})
            attempts = tuple(
                _attempt(project_root, run.branch, a, checks_of(session, a.attempt.id))
                for a in rows.attempts
            )
            total_agents += sum(r.cost_usd or 0.0 for a in attempts for r in a.agents)
            facts.append(
                TaskFact(
                    key=key,
                    title=task.get("title", key),
                    status=rows.sub_task.status,
                    size=rows.sub_task.size,
                    depends_on=tuple(key_of.get(d, d) for d in task.get("depends_on", [])),
                    criteria=tuple(task.get("acceptance_criteria", [])),
                    plan_files=tuple(task.get("files", [])),
                    expected_outcome=task.get("expected_outcome", ""),
                    attempts=attempts,
                )
            )
        return StoryFacts(
            run_id=run_id,
            story_key=run.story_key,
            story_title=title,
            status=run.status,
            branch=run.branch,
            base_commit=plan.get("config", {}).get("base_commit"),
            budget_usd=float(run.budget) if run.budget is not None else None,
            planning_cost_usd=float(run.cost or 0.0),
            agent_cost_usd=round(total_agents, 6),
            tasks=tuple(facts),
        )
