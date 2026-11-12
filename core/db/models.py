"""The 11 tables of brigade.db. Source of truth: docs/database.dbml; keep the two in step."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Money: the schema says decimal. asdecimal=False gives plain floats in Python.
Money = Numeric(12, 4, asdecimal=False)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


# ---------- Project ----------


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    repository: Mapped[str | None]  # owner/repo
    local_path: Mapped[str]
    base_branch: Mapped[str]


# ---------- Board (local copy of the tracker) ----------


class TrackerItem(Base):
    __tablename__ = "tracker_items"

    key: Mapped[str] = mapped_column(String, primary_key=True)  # Jira key or GitHub issue number
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[str]  # epic | story | sub-task
    parent_key: Mapped[str | None] = mapped_column(ForeignKey("tracker_items.key"), index=True)
    summary: Mapped[str]
    status: Mapped[str | None]
    synced_at: Mapped[datetime | None]


# ---------- Publisher ----------


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    claude_session_id: Mapped[str]
    created_at: Mapped[datetime | None]


class PublishRecord(Base):
    __tablename__ = "publish_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    proposed_items: Mapped[dict | list | None] = mapped_column(JSON)
    confirmed_at: Mapped[datetime | None]
    created_keys: Mapped[str | None]


# ---------- Planning and building ----------


class StoryRun(Base):
    __tablename__ = "story_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    story_key: Mapped[str] = mapped_column(ForeignKey("tracker_items.key"), index=True)
    # the id of the plan run (e.g. SMT-56-20261112-a3f9); the approved one is the story's run
    run_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    status: Mapped[str]  # planning | waiting | approved | superseded | failed
    branch: Mapped[str | None]
    plan_file: Mapped[str | None]  # path to plan.json
    error: Mapped[str | None] = mapped_column(Text)  # why a run failed
    budget: Mapped[float | None] = mapped_column(Money)
    cost: Mapped[float | None] = mapped_column(Money)
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]


class SubTask(Base):
    __tablename__ = "sub_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_run_id: Mapped[int] = mapped_column(ForeignKey("story_runs.id"), index=True)
    key: Mapped[str] = mapped_column(ForeignKey("tracker_items.key"), index=True)
    status: Mapped[str]  # queued | running | blocked | stopped | done | error
    depends_on: Mapped[str | None]  # comma separated keys
    size: Mapped[str | None]
    current_stage: Mapped[str | None]


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    sub_task_id: Mapped[int] = mapped_column(ForeignKey("sub_tasks.id"), index=True)
    number: Mapped[int]
    working_copy: Mapped[str | None]  # git worktree path
    outcome: Mapped[str | None]
    reason: Mapped[str | None]
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    role: Mapped[str]  # builder | tester | reviewer | planner | documenter
    model_requested: Mapped[str | None]
    model_used: Mapped[str | None]
    effort: Mapped[str | None]
    turns: Mapped[int | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cache_tokens: Mapped[int | None]
    cost: Mapped[float | None] = mapped_column(Money)
    duration_s: Mapped[int | None]
    exit_reason: Mapped[str | None]


class Check(Base):
    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    kind: Mapped[str]  # scope | tests | combined tests
    passed: Mapped[bool]
    output_tail: Mapped[str | None] = mapped_column(Text)


class Merge(Base):
    __tablename__ = "merges"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    kind: Mapped[str]  # fast-forward | real
    commit: Mapped[str | None]
    tests_passed: Mapped[bool | None]
    merged_at: Mapped[datetime | None]


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_run_id: Mapped[int] = mapped_column(ForeignKey("story_runs.id"), index=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), unique=True)
    amount: Mapped[float] = mapped_column(Money)
    released: Mapped[bool] = mapped_column(default=False)
