"""Make TestLog.panel_id nullable; add panel_name_adhoc for ad hoc test entries

Revision ID: 002_testlog_adhoc
Revises: 001_panel_test_group
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '002_testlog_adhoc'
down_revision = '001_panel_test_group'
branch_labels = None
depends_on = None


def upgrade():

    add_column('test_logs', sa.Column('panel_name_adhoc', sa.String(length=128), nullable=True))
    # panel_id nullable: only rebuild the table if it is still NOT NULL
    cols = {c['name']: c for c in sa.inspect(op.get_bind()).get_columns('test_logs')}
    if 'panel_id' in cols and not cols['panel_id']['nullable']:
        with op.batch_alter_table('test_logs', schema=None) as batch_op:
            batch_op.alter_column('panel_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table('test_logs', schema=None) as batch_op:
        batch_op.drop_column('panel_name_adhoc')
        batch_op.alter_column('panel_id', existing_type=sa.Integer(), nullable=False)
