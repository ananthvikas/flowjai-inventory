"""Add test_group to Panel; remove unique constraint from test_code

Revision ID: 001_panel_test_group
Revises:
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '001_panel_test_group'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():

    if not has_column('panels', 'test_group'):
        with op.batch_alter_table('panels', schema=None) as batch_op:
            batch_op.add_column(sa.Column('test_group', sa.String(length=64), nullable=True))
            if has_index('panels', 'ix_panels_test_code'):
                batch_op.drop_index('ix_panels_test_code')
            batch_op.create_index('ix_panels_test_code', ['test_code'], unique=False)
            batch_op.create_index('ix_panels_test_group', ['test_group'], unique=False)
    else:
        create_index('ix_panels_test_group', 'panels', ['test_group'])


def downgrade():
    with op.batch_alter_table('panels', schema=None) as batch_op:
        batch_op.drop_index('ix_panels_test_group')
        batch_op.drop_index('ix_panels_test_code')
        batch_op.create_index('ix_panels_test_code', ['test_code'], unique=True)
        batch_op.drop_column('test_group')
