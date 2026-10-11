"""
Idempotent helpers for migrations.

Some installs have a schema that is AHEAD of the version recorded in
alembic_version: the June 2026 .exe built fresh databases straight from the
models (which already had e.g. cocktails.cocktail_code) and stamped them at an
older revision. A plain add_column then fails with "duplicate column name" and
the app refuses to start. Every upgrade step therefore checks first and skips
what already exists, so a database is brought to the target schema whatever
its label says.
"""
import sqlalchemy as sa
from alembic import op


def _insp():
    return sa.inspect(op.get_bind())


def has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def has_column(table: str, column: str) -> bool:
    return has_table(table) and any(c["name"] == column for c in _insp().get_columns(table))


def has_index(table: str, name: str = None, columns=None) -> bool:
    """True if an index with this name, or any index on exactly these columns, exists."""
    if not has_table(table):
        return False
    for ix in _insp().get_indexes(table):
        if name and ix.get("name") == name:
            return True
        if columns and list(ix.get("column_names") or []) == list(columns):
            return True
    return False


def add_column(table: str, column: sa.Column) -> bool:
    """Add a column unless present. Returns True if it was added."""
    if has_column(table, column.name):
        return False
    with op.batch_alter_table(table, schema=None) as b:
        b.add_column(column)
    return True


def create_table(name: str, *cols, **kw) -> bool:
    if has_table(name):
        return False
    op.create_table(name, *cols, **kw)
    return True


def create_index(name: str, table: str, columns, **kw) -> bool:
    if has_index(table, name, columns):
        return False
    op.create_index(name, table, columns, **kw)
    return True
