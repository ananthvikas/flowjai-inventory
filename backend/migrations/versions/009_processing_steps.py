"""Bench processing station: step templates per panel, per-tube step progress,
and a link from cocktail usage to the worklist tube that consumed it.

Revision ID: 009_processing_steps
Revises: 008_staff_signatures
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '009_processing_steps'
down_revision = '008_staff_signatures'
branch_labels = None
depends_on = None


def upgrade():
    create_table(
        'panel_process_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('panel_id', sa.Integer(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['panel_id'], ['panels.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_panel_process_steps_panel_id', 'panel_process_steps', ['panel_id'])

    create_table(
        'sample_order_tube_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tube_id', sa.Integer(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_by_staff_id', sa.Integer(), nullable=True),
        sa.Column('completed_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['tube_id'], ['sample_order_tubes.id']),
        sa.ForeignKeyConstraint(['completed_by_staff_id'], ['staff.id']),
        sa.ForeignKeyConstraint(['completed_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_sample_order_tube_steps_tube_id', 'sample_order_tube_steps', ['tube_id'])

    if not has_column('cocktail_usage_logs', 'sample_order_tube_id'):
        with op.batch_alter_table('cocktail_usage_logs', schema=None) as batch_op:
            batch_op.add_column(sa.Column('sample_order_tube_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_cocktail_usage_logs_tube', 'sample_order_tubes', ['sample_order_tube_id'], ['id'])
    create_index('ix_cocktail_usage_logs_sample_order_tube_id', 'cocktail_usage_logs', ['sample_order_tube_id'])


def downgrade():
    op.drop_index('ix_cocktail_usage_logs_sample_order_tube_id', 'cocktail_usage_logs')
    with op.batch_alter_table('cocktail_usage_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cocktail_usage_logs_tube', type_='foreignkey')
        batch_op.drop_column('sample_order_tube_id')
    op.drop_index('ix_sample_order_tube_steps_tube_id', 'sample_order_tube_steps')
    op.drop_table('sample_order_tube_steps')
    op.drop_index('ix_panel_process_steps_panel_id', 'panel_process_steps')
    op.drop_table('panel_process_steps')
