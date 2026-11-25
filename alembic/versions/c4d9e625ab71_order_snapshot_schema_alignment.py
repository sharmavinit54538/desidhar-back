"""Align order snapshot storage and payment provider uniqueness.

Revision ID: c4d9e625ab71
Revises: b8c54d109e72
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d9e625ab71"
down_revision = "b8c54d109e72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen safely; existing snapshots remain unchanged.
    op.alter_column("order_items", "sku_snapshot", existing_type=sa.String(100), type_=sa.String(220), existing_nullable=True)
    op.alter_column("order_items", "image_url_snapshot", existing_type=sa.String(1000), type_=sa.String(2048), existing_nullable=True)
    op.alter_column("orders", "status", existing_type=sa.String(16), type_=sa.String(30), existing_nullable=False)
    op.create_unique_constraint("uq_payments_provider_payment", "payments", ["provider", "provider_payment_id"])


def downgrade() -> None:
    op.drop_constraint("uq_payments_provider_payment", "payments", type_="unique")
    op.alter_column("orders", "status", existing_type=sa.String(30), type_=sa.String(16), existing_nullable=False)
    op.alter_column("order_items", "image_url_snapshot", existing_type=sa.String(2048), type_=sa.String(1000), existing_nullable=True)
    op.alter_column("order_items", "sku_snapshot", existing_type=sa.String(220), type_=sa.String(100), existing_nullable=True)
