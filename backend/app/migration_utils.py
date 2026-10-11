"""
Helpers that make migrations safe to re-run on a database whose schema is
ahead of its recorded version (tables/columns already created by an earlier
start-up). Each op checks the live schema first and skips what already exists.
"""

import sqlalchemy as sa
from alembic import op


def _insp():
    return sa.inspect(op.get_bind())


def has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def has_column(table: str, column: str) -> bool:
    return has_table(table) and column in {c["name"] for c in _insp().get_columns(table)}


def has_index(table: str, index: str) -> bool:
    return has_table(table) and index in {i["name"] for i in _insp().get_indexes(table)}


def create_index(name: str, table: str, columns) -> None:
    if not has_index(table, name):
        op.create_index(name, table, columns)


def add_column(table: str, column: sa.Column, fk=None) -> None:
    """Add a column (and optionally a named FK) unless the column already exists.
    fk = (constraint_name, referred_table, [local_cols], [remote_cols])"""
    if has_column(table, column.name):
        return
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.add_column(column)
        if fk:
            batch_op.create_foreign_key(*fk)
