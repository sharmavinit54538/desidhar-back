"""Add idempotent collection and refund processing fields.

Revision ID: b8c54d109e72
Revises: a91f30d2b6c4
"""
from alembic import op
import sqlalchemy as sa

revision = "b8c54d109e72"
down_revision = "a91f30d2b6c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("image_url_snapshot", sa.String(1000), nullable=True))
    op.add_column("order_items", sa.Column("sku_snapshot", sa.String(100), nullable=True))
    op.add_column("payments", sa.Column("collected_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("payments", sa.Column("collection_method", sa.String(30), nullable=True))
    op.add_column("payments", sa.Column("collection_reference", sa.String(100), nullable=True))
    op.add_column("payments", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_payments_order_idempotency", "payments", ["order_id", "idempotency_key"])
    op.add_column("refunds", sa.Column("status", sa.String(20), server_default="pending", nullable=False))
    op.add_column("refunds", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column("refunds", sa.Column("provider_refund_id", sa.String(100), nullable=True))
    op.add_column("refunds", sa.Column("failure_reason", sa.String(255), nullable=True))
    op.add_column("refunds", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refunds", sa.Column("reference", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_refunds_order_idempotency", "refunds", ["order_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_refunds_order_idempotency", "refunds", type_="unique")
    for col in ("reference", "completed_at", "failure_reason", "provider_refund_id", "idempotency_key", "status"):
        op.drop_column("refunds", col)
    op.drop_constraint("uq_payments_order_idempotency", "payments", type_="unique")
    for col in ("idempotency_key", "collection_reference", "collection_method", "collected_by"):
        op.drop_column("payments", col)
    op.drop_column("order_items", "sku_snapshot")
    op.drop_column("order_items", "image_url_snapshot")
