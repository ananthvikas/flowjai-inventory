"""Add sample-order worklist: staff master list, sample_orders, sample_order_tubes,
and cocktail reservation counter.

Revision ID: 005_sample_orders
Revises: 004_verification_method
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '005_sample_orders'
down_revision = '004_verification_method'
branch_labels = None
depends_on = None


def upgrade():
    # Reservation counter on cocktails
    add_column('cocktails', sa.Column('reserved_tests', sa.Integer(), nullable=False, server_default='0'))

    # Staff master list (pathologists + technologists)
    create_table(
        'staff',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False, server_default='technologist'),
        sa.Column('initials', sa.String(length=16), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_staff_name', 'staff', ['name'])
    create_index('ix_staff_role', 'staff', ['role'])

    # Sample orders (worklist header)
    create_table(
        'sample_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lab_id', sa.String(length=64), nullable=False),
        sa.Column('requesting_pathologist_id', sa.Integer(), nullable=True),
        sa.Column('processing_technologist_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='in_queue'),
        sa.Column('priority', sa.String(length=16), nullable=False, server_default='routine'),
        sa.Column('notes', sa.String(length=512), nullable=True),
        sa.Column('ordered_at', sa.DateTime(), nullable=False),
        sa.Column('processing_started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['requesting_pathologist_id'], ['staff.id']),
        sa.ForeignKeyConstraint(['processing_technologist_id'], ['staff.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_sample_orders_lab_id', 'sample_orders', ['lab_id'])
    create_index('ix_sample_orders_status', 'sample_orders', ['status'])
    create_index('ix_sample_orders_ordered_at', 'sample_orders', ['ordered_at'])

    # Sample order tubes (line items)
    create_table(
        'sample_order_tubes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sample_order_id', sa.Integer(), nullable=False),
        sa.Column('panel_id', sa.Integer(), nullable=False),
        sa.Column('reserved_cocktail_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='awaiting_cocktail'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sample_order_id'], ['sample_orders.id']),
        sa.ForeignKeyConstraint(['panel_id'], ['panels.id']),
        sa.ForeignKeyConstraint(['reserved_cocktail_id'], ['cocktails.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_sample_order_tubes_order', 'sample_order_tubes', ['sample_order_id'])
    create_index('ix_sample_order_tubes_panel', 'sample_order_tubes', ['panel_id'])
    create_index('ix_sample_order_tubes_cocktail', 'sample_order_tubes', ['reserved_cocktail_id'])


def downgrade():
    op.drop_index('ix_sample_order_tubes_cocktail', 'sample_order_tubes')
    op.drop_index('ix_sample_order_tubes_panel', 'sample_order_tubes')
    op.drop_index('ix_sample_order_tubes_order', 'sample_order_tubes')
    op.drop_table('sample_order_tubes')

    op.drop_index('ix_sample_orders_ordered_at', 'sample_orders')
    op.drop_index('ix_sample_orders_status', 'sample_orders')
    op.drop_index('ix_sample_orders_lab_id', 'sample_orders')
    op.drop_table('sample_orders')

    op.drop_index('ix_staff_role', 'staff')
    op.drop_index('ix_staff_name', 'staff')
    op.drop_table('staff')

    with op.batch_alter_table('cocktails', schema=None) as batch_op:
        batch_op.drop_column('reserved_tests')
