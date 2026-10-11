"""Record the person (staff) behind shared-login actions:
cocktails.prepared_by_staff_id, shipment_verifications.closed_by_staff_id.

Revision ID: 008_staff_signatures
Revises: 007_shipment_verification
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '008_staff_signatures'
down_revision = '007_shipment_verification'
branch_labels = None
depends_on = None


def upgrade():

    if not has_column('cocktails', 'prepared_by_staff_id'):
        with op.batch_alter_table('cocktails', schema=None) as batch_op:
            batch_op.add_column(sa.Column('prepared_by_staff_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_cocktails_prepared_by_staff', 'staff', ['prepared_by_staff_id'], ['id'])
    create_index('ix_cocktails_prepared_by_staff_id', 'cocktails', ['prepared_by_staff_id'])

    if not has_column('shipment_verifications', 'closed_by_staff_id'):
        with op.batch_alter_table('shipment_verifications', schema=None) as batch_op:
            batch_op.add_column(sa.Column('closed_by_staff_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_shipment_verifications_closed_by_staff', 'staff', ['closed_by_staff_id'], ['id'])


def downgrade():
    with op.batch_alter_table('shipment_verifications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_shipment_verifications_closed_by_staff', type_='foreignkey')
        batch_op.drop_column('closed_by_staff_id')
    op.drop_index('ix_cocktails_prepared_by_staff_id', 'cocktails')
    with op.batch_alter_table('cocktails', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cocktails_prepared_by_staff', type_='foreignkey')
        batch_op.drop_column('prepared_by_staff_id')
