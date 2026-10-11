"""Add measurement-method metadata to verification logs and per-vial tare to stock lots

Revision ID: 004_verification_method
Revises: 003_store_stock
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '004_verification_method'
down_revision = '003_store_stock'
branch_labels = None
depends_on = None


def upgrade():

    add_column('verification_logs', sa.Column('measurement_method', sa.String(length=32), nullable=False, server_default='pipette'))
    add_column('verification_logs', sa.Column('pipette_increment_ul', sa.Float(), nullable=True))
    add_column('verification_logs', sa.Column('verification_cycle', sa.String(length=64), nullable=True))
    add_column('stock_lots', sa.Column('empty_vial_tare_g', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('stock_lots', schema=None) as batch_op:
        batch_op.drop_column('empty_vial_tare_g')
    with op.batch_alter_table('verification_logs', schema=None) as batch_op:
        batch_op.drop_column('verification_cycle')
        batch_op.drop_column('pipette_increment_ul')
        batch_op.drop_column('measurement_method')
