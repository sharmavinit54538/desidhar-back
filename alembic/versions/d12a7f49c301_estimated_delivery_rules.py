"""Add configurable delivery estimates and order date snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d12a7f49c301"
down_revision = "ac8f2d2cb09a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shipping_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pincode", sa.String(6)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(100)),
        sa.Column("shipping_zone", sa.String(100)),
        sa.Column("standard_days", sa.Integer(), server_default="5", nullable=False),
        sa.Column("express_days", sa.Integer()),
        sa.Column("working_weekdays", sa.JSON(), server_default=sa.text("'[0,1,2,3,4,5]'"), nullable=False),
        sa.Column("holidays", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("standard_days >= 0", name="ck_shipping_rule_standard_days"),
        sa.CheckConstraint("express_days IS NULL OR express_days >= 0", name="ck_shipping_rule_express_days"),
    )
    for column in ("pincode", "city", "state", "shipping_zone"):
        op.create_index(f"ix_shipping_rules_{column}", "shipping_rules", [column])
    op.add_column("pincodes", sa.Column("shipping_zone", sa.String(100), nullable=True))
    op.add_column("products", sa.Column("processing_days", sa.Integer(), server_default="1", nullable=False))
    op.create_check_constraint("ck_product_processing_days_non_negative", "products", "processing_days >= 0")
    op.add_column("orders", sa.Column("estimated_delivery_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("estimated_delivery_end_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("revised_delivery_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("delay_reason", sa.String(500), nullable=True))
    op.add_column("orders", sa.Column("delivery_speed", sa.String(20), server_default="standard", nullable=False))


def downgrade() -> None:
    op.drop_column("orders", "delivery_speed")
    op.drop_column("orders", "delay_reason")
    op.drop_column("orders", "revised_delivery_date")
    op.drop_column("orders", "estimated_delivery_end_date")
    op.drop_column("orders", "estimated_delivery_date")
    op.drop_constraint("ck_product_processing_days_non_negative", "products", type_="check")
    op.drop_column("products", "processing_days")
    op.drop_column("pincodes", "shipping_zone")
    for column in ("shipping_zone", "state", "city", "pincode"):
        op.drop_index(f"ix_shipping_rules_{column}", table_name="shipping_rules")
    op.drop_table("shipping_rules")
