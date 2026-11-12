"""Bring an older brigade.db up to the models without losing anything.

``create_all`` makes missing tables but never touches a table that exists, so a column added to
a model later (story_runs.run_id, story_runs.error) would be missing from a database made
before it. This adds such columns and their indexes. It only adds: nothing is dropped, renamed
or changed. A new column must allow empty values, since the rows already there have none.
"""

from sqlalchemy import Engine, inspect, text

from core.db.models import Base


class UpgradeError(RuntimeError):
    """The database cannot be brought up to the models by adding columns."""


def add_missing_columns(engine: Engine) -> list[str]:
    """Add every model column an existing table lacks. Returns them as table.column."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    added: list[str] = []
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue
            have = {column["name"] for column in inspector.get_columns(table.name)}
            missing = [column for column in table.columns if column.name not in have]
            for column in missing:
                if not column.nullable or column.primary_key:
                    raise UpgradeError(
                        f"{table.name}.{column.name} cannot be added to an existing database "
                        "because it may not be empty. Back up brigade.db and start a new one."
                    )
                kind = column.type.compile(dialect=engine.dialect)
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}')
                )
                added.append(f"{table.name}.{column.name}")
            if missing:
                for index in table.indexes:
                    index.create(connection, checkfirst=True)
    return added
