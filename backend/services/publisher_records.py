"""Reading and clearing the stored plans of a Publisher chat."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.db.models import PublishRecord
from pipeline.publisher.publish import Created


def open_proposal(session: Session, chat_id: int) -> PublishRecord | None:
    return session.scalars(
        select(PublishRecord)
        .where(PublishRecord.chat_session_id == chat_id, PublishRecord.confirmed_at.is_(None))
        .order_by(PublishRecord.id.desc())
    ).first()


def withdraw_open_proposal(session: Session, chat_id: int) -> None:
    session.execute(
        delete(PublishRecord).where(
            PublishRecord.chat_session_id == chat_id, PublishRecord.confirmed_at.is_(None)
        )
    )


def confirmed_records(session: Session, chat_id: int) -> list[PublishRecord]:
    """The plans of this chat that were confirmed, oldest first."""
    return list(
        session.scalars(
            select(PublishRecord)
            .where(
                PublishRecord.chat_session_id == chat_id, PublishRecord.confirmed_at.is_not(None)
            )
            .order_by(PublishRecord.id)
        )
    )


def last_confirmed(session: Session, chat_id: int) -> PublishRecord | None:
    return session.scalars(
        select(PublishRecord)
        .where(PublishRecord.chat_session_id == chat_id, PublishRecord.confirmed_at.is_not(None))
        .order_by(PublishRecord.id.desc())
    ).first()


def confirmed_keys(session: Session, chat_id: int) -> list[str]:
    values = session.scalars(
        select(PublishRecord.created_keys)
        .where(PublishRecord.chat_session_id == chat_id, PublishRecord.created_keys.is_not(None))
        .order_by(PublishRecord.id)
    )
    return [key for value in values for key in (value or "").split(",") if key]


def created_from(record: PublishRecord, keys: list[str]) -> list[Created]:
    """The created items again, from the stored plan and keys (same order as creation)."""
    items: list[Created] = []
    plan = record.proposed_items
    if not isinstance(plan, dict):
        return items
    stories = plan.get("stories") or []
    remaining = iter(keys)
    for story in stories:
        story_key = next(remaining, None)
        if story_key is None:
            break
        items.append(Created("story", story_key, story["summary"], story["epic"]))
        for subtask in story.get("subtasks") or []:
            key = next(remaining, None)
            if key is None:
                return items
            items.append(Created("sub-task", key, subtask["summary"], story_key))
    return items
