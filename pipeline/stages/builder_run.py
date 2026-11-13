"""One Builder attempt of one sub-task, inside its own worktree. Nothing is committed or merged.

build_attempt   prepare the attempt worktree (a branch from the story tip, the setup lines), run
                the Builder there, record the database rows, and measure what changed

The orchestrator, not the Builder, says what happened: the changed files come from Git, the usage
from Claude Code's result. Judging the work (the diff against Files, the checks, the Reviewer)
and committing it are the next steps. The project's own folder is compared before and after.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core.db import get_session, init_db
from core.db.models import AgentRun, Attempt, SubTask
from core.db.repositories import attempt_rows
from core.db.repositories import story_runs as runs
from core.db.repositories.projects import sync_env_project
from core.settings import Settings
from pipeline.planning.profiles import profile_for, role_settings
from pipeline.runner.claude_runner import AgentError, AgentReply, AgentRunner
from pipeline.stages.builder_prompt import builder_prompt
from pipeline.stages.builder_report import BuildResult
from pipeline.stages.builder_session import builder_request
from pipeline.stages.prepare import approved_plan, prepare_attempt, project_root
from pipeline.workspace.git import changed_files, repository_state

Row = TypeVar("Row")


class BuildError(RuntimeError):
    """The attempt was refused before anything ran. The message says why."""


def _row(session: Session, model: type[Row], row_id: int) -> Row:
    """A row we wrote a moment ago; it being gone is a bug, not a user error."""
    row = session.get(model, row_id)
    if row is None:
        raise BuildError(f"The {model.__name__} row {row_id} vanished from the database.")
    return row


def _now() -> datetime:
    return datetime.now(UTC)


def _task(plan: dict[str, Any], key: str) -> dict[str, Any]:
    for task in plan["tasks"]:
        if task.get("jira_key") == key:
            return task
    raise BuildError(f"{key} is not a task of run {plan.get('run_id')}.")


def _limits(task: dict[str, Any]) -> dict[str, Any]:
    chosen = role_settings(profile_for(task["complexity"]), "builder")
    return {
        "model": chosen.model,
        "effort": chosen.effort,
        "max_turns": chosen.max_turns,
        "max_budget_usd": chosen.max_budget_usd,
    }


def _usage(reply: AgentReply) -> dict[str, Any]:
    seconds = None if reply.duration_ms is None else round(reply.duration_ms / 1000, 1)
    return {
        "session_id": reply.session_id,
        "cost_usd": reply.cost_usd,
        "turns": reply.turns,
        "seconds": seconds,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "cache_tokens": reply.cache_tokens,
        "model_used": reply.model_used,
    }


def _sub_task_id(
    engine: Engine, settings: Settings, plan: dict[str, Any], task: dict[str, Any], run_id: str
) -> int:
    """The sub_tasks row for this task, made if needed. Refuses a run the database lacks."""
    by_id = {t["id"]: t.get("jira_key") or t["id"] for t in plan["tasks"]}
    waits_for = [by_id.get(i, i) for i in task.get("depends_on", [])]
    with get_session(engine) as session:
        project = sync_env_project(session, settings)
        story = runs.get_run(session, project.id, run_id) if project else None
        if story is None or story.status != runs.APPROVED:
            raise BuildError(f"Run {run_id} is not an approved run in the database: plan it first.")
        try:
            row = attempt_rows.sub_task_row(
                session, story.id, task["jira_key"], task["complexity"], waits_for
            )
        except attempt_rows.BuildRecordError as exc:
            raise BuildError(str(exc)) from None
        return row.id


def _ask_builder(
    runner: AgentRunner,
    plan: dict[str, Any],
    task: dict[str, Any],
    worktree: Path,
    root: Path,
    session_id: str,
) -> tuple[AgentReply | None, str | None]:
    """Run the Builder. (reply, error); an error also when the project's own folder changed."""
    before = repository_state(root)
    prompt = builder_prompt(task)
    request = builder_request(task, plan["commands"], prompt, worktree, root, session_id)
    reply, error = None, None
    try:
        reply = runner.run(request)
    except AgentError as exc:
        error = str(exc)
    if repository_state(root) != before:
        error = (
            "The project's own folder changed while the Builder ran. It may have broken its rule "
            "to stay in its worktree: look at git status in the project folder."
        )
    return reply, error


def build_attempt(
    settings: Settings,
    run_id: str,
    key: str,
    runner: AgentRunner,
    number: int = 1,
    engine: Engine | None = None,
) -> BuildResult:
    """Prepare the worktree, run the Builder, record it. BuildError/PrepareError: refused."""
    root = project_root(settings)
    plan = approved_plan(root, run_id)
    task = _task(plan, key)
    engine = init_db(engine)
    sub_task_id = _sub_task_id(engine, settings, plan, task, run_id)
    ready = prepare_attempt(settings, run_id, key, number)
    result = BuildResult(
        run_id, key, number, ready.branch, ready.worktree, _limits(task), setup=ready.setup
    )
    with get_session(engine) as session:
        attempt = attempt_rows.start_attempt(
            session,
            _row(session, SubTask, sub_task_id),
            number,
            ready.branch,
            ready.worktree,
            _now(),
        )
        attempt_id = attempt.id
    reply, run_row_id = None, None
    if ready.ok:
        session_id = str(uuid.uuid4())
        with get_session(engine) as session:
            row = attempt_rows.start_agent_run(
                session, attempt, "builder", result.limits["model"], result.limits["effort"],
                session_id, _now(),
            )  # fmt: skip
            run_row_id = row.id
        reply, result.error = _ask_builder(
            runner, plan, task, Path(ready.worktree), root, session_id
        )
    else:
        result.error = "setup failed in the attempt worktree, so no Builder was started."
    result.changed = changed_files(Path(ready.worktree))
    if reply is not None:
        result.usage, result.report = _usage(reply), reply.text
    with get_session(engine) as session:
        if run_row_id is not None:
            attempt_rows.finish_agent_run(
                session, _row(session, AgentRun, run_row_id), reply, error=result.error, now=_now()
            )
        failed = result.error is not None
        attempt_rows.finish_attempt(
            session, _row(session, Attempt, attempt_id), _row(session, SubTask, sub_task_id),
            outcome="error" if failed else "built", reason=result.error, stage="builder",
            status=attempt_rows.ERROR if failed else attempt_rows.RUNNING, now=_now(),
        )  # fmt: skip
    return result
