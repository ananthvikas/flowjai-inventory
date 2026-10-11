"""Standard vial volume on the antibody master, audit notes on stock lots, and a
sample-quality comment on worklist orders.

Revision ID: 011_vial_volume_sample_comment
Revises: 010_step_timers
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column  # noqa: F401

revision = '011_vial_volume_sample_comment'
down_revision = '010_step_timers'
branch_labels = None
depends_on = None


def upgrade():
    add_column('antibodies', sa.Column('vial_volume_ul', sa.Float(), nullable=True))
    add_column('stock_lots', sa.Column('notes', sa.String(length=1024), nullable=True))
    add_column('sample_orders', sa.Column('sample_comment', sa.String(length=512), nullable=True))
    add_column('sample_orders', sa.Column('sample_comment_updated_at', sa.DateTime(), nullable=True))
    # No FK constraint here: adding one would force a SQLite table rebuild of
    # sample_orders. The model declares the FK; integrity is enforced in the app.
    add_column('sample_orders', sa.Column('sample_comment_updated_by', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('sample_orders', schema=None) as b:
        b.drop_column('sample_comment_updated_by')
        b.drop_column('sample_comment_updated_at')
        b.drop_column('sample_comment')
    with op.batch_alter_table('stock_lots', schema=None) as b:
        b.drop_column('notes')
    with op.batch_alter_table('antibodies', schema=None) as b:
        b.drop_column('vial_volume_ul')
