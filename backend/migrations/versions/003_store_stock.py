"""Add store_stock table for whole-vial stockroom tracking

Revision ID: 003_store_stock
Revises: 002_testlog_adhoc
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '003_store_stock'
down_revision = '002_testlog_adhoc'
branch_labels = None
depends_on = None


def upgrade():

    create_table(
        'store_stock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('antibody_id', sa.Integer(), nullable=False),
        sa.Column('lot_no', sa.String(length=64), nullable=False),
        sa.Column('vendor', sa.String(length=128), nullable=True),
        sa.Column('catalog_no', sa.String(length=64), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('volume_per_vial_ul', sa.Float(), nullable=False, server_default='500.0'),
        sa.Column('received_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['antibody_id'], ['antibodies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_store_stock_antibody_id', 'store_stock', ['antibody_id'])


def downgrade():
    op.drop_index('ix_store_stock_antibody_id', 'store_stock')
    op.drop_table('store_stock')
