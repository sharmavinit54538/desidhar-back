"""Add verified cash collections, custody settlements, and delivery OTPs.

Revision ID: ac8f2d2cb09a
Revises: ab18d190e4f2
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "ac8f2d2cb09a"
down_revision: Union[str, None] = "ab18d190e4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("delivery_cod_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False), sa.Column("method", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False), sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("partner_id", "idempotency_key", name="uq_delivery_collection_partner_idempotency"),
        sa.CheckConstraint("amount_paise > 0", name="ck_delivery_collection_amount_positive"))
    op.create_index("ix_delivery_cod_collections_partner", "delivery_cod_collections", ["partner_id", "collected_at"])
    op.create_table("delivery_cash_settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("expected_amount_paise", sa.Integer(), nullable=False), sa.Column("verified_amount_paise", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), server_default="submitted", nullable=False),
        sa.Column("submission_note", sa.String(255), nullable=True), sa.Column("deposit_reference", sa.String(100), nullable=True),
        sa.Column("review_note", sa.String(255), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expected_amount_paise > 0", name="ck_delivery_settlement_amount_positive"))
    op.create_table("delivery_cash_settlement_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("settlement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_cash_settlements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_cod_collections.id", ondelete="RESTRICT"), nullable=False, unique=True))
    op.create_table("delivery_otps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False), sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_delivery_otp_attempts"))
    op.create_index("ix_delivery_otp_order_created", "delivery_otps", ["order_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_delivery_otp_order_created", table_name="delivery_otps")
    op.drop_table("delivery_otps")
    op.drop_table("delivery_cash_settlement_items")
    op.drop_table("delivery_cash_settlements")
    op.drop_index("ix_delivery_cod_collections_partner", table_name="delivery_cod_collections")
    op.drop_table("delivery_cod_collections")
