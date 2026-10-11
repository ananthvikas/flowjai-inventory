"""Step timers: wait_minutes on step templates and per-tube steps, and a record
of steps completed before their timer ran out.

Revision ID: 010_step_timers
Revises: 009_processing_steps
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '010_step_timers'
down_revision = '009_processing_steps'
branch_labels = None
depends_on = None


def upgrade():

    add_column('panel_process_steps', sa.Column('wait_minutes', sa.Integer(), nullable=True))
    add_column('sample_order_tube_steps', sa.Column('wait_minutes', sa.Integer(), nullable=True))
    add_column('sample_order_tube_steps', sa.Column('completed_early_seconds', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('sample_order_tube_steps', schema=None) as b:
        b.drop_column('completed_early_seconds')
        b.drop_column('wait_minutes')
    with op.batch_alter_table('panel_process_steps', schema=None) as b:
        b.drop_column('wait_minutes')
