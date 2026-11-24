"""Persist fulfillment lifecycle and order events.

Revision ID: a91f30d2b6c4
Revises: f47a1928bc01
"""
from alembic import op
import sqlalchemy as sa

revision = "a91f30d2b6c4"
down_revision = "f47a1928bc01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("invoices",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("order_id", sa.UUID(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=False),
        sa.Column("invoice_number", sa.String(40), unique=True, nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False))
    op.add_column("orders", sa.Column("packed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("out_for_delivery_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("orders", sa.Column("stock_reserved", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("orders", sa.Column("stock_released", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("orders", sa.Column("return_restocked", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("orders", sa.Column("billing_address", sa.JSON(), nullable=True))
    op.add_column("order_status_history", sa.Column("actor_type", sa.String(20), server_default="system", nullable=False))
    op.add_column("order_status_history", sa.Column("reason", sa.String(255), nullable=True))
    op.add_column("order_status_history", sa.Column("customer_visible_message", sa.String(500), nullable=True))
    op.add_column("order_status_history", sa.Column("internal_admin_note", sa.Text(), nullable=True))
    op.add_column("order_status_history", sa.Column("event_source", sa.String(30), server_default="legacy", nullable=False))
    op.add_column("order_status_history", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column("order_status_history", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_order_history_idempotency", "order_status_history", ["order_id", "idempotency_key"])
    op.create_table("shipments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("order_id", sa.UUID(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=False),
        sa.Column("courier_name", sa.String(100), nullable=False), sa.Column("tracking_number", sa.String(150)),
        sa.Column("tracking_url", sa.String(2048)), sa.Column("shipment_reference", sa.String(150), nullable=False),
        sa.Column("shipment_status", sa.String(30), nullable=False), sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True)), sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_failure_reason", sa.String(255)), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("inventory_transactions",
        sa.Column("id", sa.UUID(), primary_key=True), sa.Column("order_id", sa.UUID(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.UUID(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False), sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("changed_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("reason", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "product_id", "operation", name="uq_inventory_order_operation"),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_inventory_nonzero"))
    op.create_table("order_operations",
        sa.Column("id", sa.UUID(), primary_key=True), sa.Column("order_id", sa.UUID(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False), sa.Column("action", sa.String(50), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "idempotency_key", name="uq_order_operation_idempotency"))
    op.create_table("order_notifications",
        sa.Column("id", sa.UUID(), primary_key=True), sa.Column("order_id", sa.UUID(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False), sa.Column("event_key", sa.String(150), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False), sa.Column("recipient", sa.String(255)), sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False), sa.Column("last_error", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("order_id", "event_key", "channel", name="uq_notification_event_channel"))
    op.create_index("ix_notifications_pending", "order_notifications", ["status", "next_attempt_at"])
    op.create_index("ix_notifications_user", "order_notifications", ["user_id", "created_at"])
    op.create_table("order_audit_logs",
        sa.Column("id", sa.UUID(), primary_key=True), sa.Column("order_id", sa.UUID(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("action", sa.String(50), nullable=False), sa.Column("event_key", sa.String(150), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "event_key", name="uq_audit_order_event"))


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_table("order_audit_logs")
    op.drop_index("ix_notifications_user", table_name="order_notifications")
    op.drop_index("ix_notifications_pending", table_name="order_notifications")
    op.drop_table("order_notifications")
    op.drop_table("order_operations")
    op.drop_table("inventory_transactions")
    op.drop_table("shipments")
    op.drop_constraint("uq_order_history_idempotency", "order_status_history", type_="unique")
    for col in ("request_fingerprint", "idempotency_key", "event_source", "internal_admin_note", "customer_visible_message", "reason", "actor_type"):
        op.drop_column("order_status_history", col)
    for col in ("billing_address", "return_restocked", "stock_released", "stock_reserved", "version", "out_for_delivery_at", "shipped_at", "packed_at"):
        op.drop_column("orders", col)
