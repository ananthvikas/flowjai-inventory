"""Staff name behind sample comments, and tap-to-toggle sample quality flags.

Revision ID: 012_sample_flags_comment_staff
Revises: 011_vial_volume_sample_comment
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column  # noqa: F401

revision = '012_sample_flags_comment_staff'
down_revision = '011_vial_volume_sample_comment'
branch_labels = None
depends_on = None


def upgrade():
    # Plain integer columns (no FK constraint) to avoid a SQLite rebuild of
    # sample_orders; the model declares the FKs and the API validates staff ids.
    add_column('sample_orders', sa.Column('sample_comment_staff_id', sa.Integer(), nullable=True))
    add_column('sample_orders', sa.Column('sample_flags', sa.String(length=128), nullable=True))
    add_column('sample_orders', sa.Column('sample_flags_updated_at', sa.DateTime(), nullable=True))
    add_column('sample_orders', sa.Column('sample_flags_staff_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('sample_orders', schema=None) as b:
        b.drop_column('sample_flags_staff_id')
        b.drop_column('sample_flags_updated_at')
        b.drop_column('sample_flags')
        b.drop_column('sample_comment_staff_id')
