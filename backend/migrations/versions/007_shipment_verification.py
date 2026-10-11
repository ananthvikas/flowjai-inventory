"""Shipment traceability: stock_lots.shipment_id, shipment_verifications,
shipment_verification_attachments.

Revision ID: 007_shipment_verification
Revises: 006_model_columns
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

from _guards import add_column, create_index, create_table, has_column, has_index, has_table  # noqa: F401

revision = '007_shipment_verification'
down_revision = '006_model_columns'
branch_labels = None
depends_on = None


def upgrade():
    add_column('stock_lots', sa.Column('shipment_id', sa.String(length=64), nullable=True))
    create_index('ix_stock_lots_shipment_id', 'stock_lots', ['shipment_id'])

    # Back-fill: lots opened from store stock before this release lost the
    # shipment ID. Where exactly one store row matches antibody + lot number and
    # it has a shipment ID, carry it over. Ambiguous matches are left blank.
    op.execute("""
        UPDATE stock_lots
        SET shipment_id = (
            SELECT ss.shipment_id FROM store_stock ss
            WHERE ss.antibody_id = stock_lots.antibody_id
              AND ss.lot_no = stock_lots.lot_no
              AND ss.shipment_id IS NOT NULL
        )
        WHERE shipment_id IS NULL
          AND (
            SELECT COUNT(DISTINCT ss.shipment_id) FROM store_stock ss
            WHERE ss.antibody_id = stock_lots.antibody_id
              AND ss.lot_no = stock_lots.lot_no
              AND ss.shipment_id IS NOT NULL
          ) = 1
    """)

    create_table(
        'shipment_verifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('antibody_id', sa.Integer(), nullable=False),
        sa.Column('shipment_id', sa.String(length=64), nullable=False),
        sa.Column('new_lot_no', sa.String(length=64), nullable=True),
        sa.Column('previous_shipment_id', sa.String(length=64), nullable=True),
        sa.Column('previous_lot_no', sa.String(length=64), nullable=True),
        sa.Column('lot_changed', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='open'),
        sa.Column('triggered_at', sa.DateTime(), nullable=False),
        sa.Column('due_at', sa.DateTime(), nullable=False),
        sa.Column('triggered_by', sa.Integer(), nullable=True),
        sa.Column('outcome', sa.String(length=32), nullable=True),
        sa.Column('comments', sa.String(length=1024), nullable=True),
        sa.Column('closed_by', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('alert_id', sa.Integer(), nullable=True),
        sa.Column('overdue_alert_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['antibody_id'], ['antibodies.id']),
        sa.ForeignKeyConstraint(['triggered_by'], ['users.id']),
        sa.ForeignKeyConstraint(['closed_by'], ['users.id']),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.id']),
        sa.ForeignKeyConstraint(['overdue_alert_id'], ['alerts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_shipment_verifications_antibody_id', 'shipment_verifications', ['antibody_id'])
    create_index('ix_shipment_verifications_shipment_id', 'shipment_verifications', ['shipment_id'])
    create_index('ix_shipment_verifications_status', 'shipment_verifications', ['status'])

    create_table(
        'shipment_verification_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('verification_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['verification_id'], ['shipment_verifications.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    create_index('ix_shipment_verification_attachments_verification_id',
                    'shipment_verification_attachments', ['verification_id'])


def downgrade():
    op.drop_index('ix_shipment_verification_attachments_verification_id', 'shipment_verification_attachments')
    op.drop_table('shipment_verification_attachments')
    op.drop_index('ix_shipment_verifications_status', 'shipment_verifications')
    op.drop_index('ix_shipment_verifications_shipment_id', 'shipment_verifications')
    op.drop_index('ix_shipment_verifications_antibody_id', 'shipment_verifications')
    op.drop_table('shipment_verifications')
    op.drop_index('ix_stock_lots_shipment_id', 'stock_lots')
    with op.batch_alter_table('stock_lots', schema=None) as batch_op:
        batch_op.drop_column('shipment_id')
