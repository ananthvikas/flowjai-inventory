"""Sync models: add cocktails.cocktail_code and store_stock.shipment_id

Revision ID: 006_model_columns
Revises: 005_sample_orders
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '006_model_columns'
down_revision = '005_sample_orders'
branch_labels = None
depends_on = None


def upgrade():

    add_column('cocktails', sa.Column('cocktail_code', sa.String(length=64), nullable=True))
    create_index('ix_cocktails_cocktail_code', 'cocktails', ['cocktail_code'], unique=True)
    add_column('store_stock', sa.Column('shipment_id', sa.String(length=64), nullable=True))
    create_index('ix_store_stock_shipment_id', 'store_stock', ['shipment_id'])


def downgrade():
    op.drop_index('ix_store_stock_shipment_id', 'store_stock')
    op.drop_index('ix_cocktails_cocktail_code', 'cocktails')
    with op.batch_alter_table('store_stock', schema=None) as batch_op:
        batch_op.drop_column('shipment_id')
    with op.batch_alter_table('cocktails', schema=None) as batch_op:
        batch_op.drop_column('cocktail_code')
