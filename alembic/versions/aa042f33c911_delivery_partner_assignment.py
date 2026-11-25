"""Add delivery partner profiles and transactional assignments.

Revision ID: aa042f33c911
Revises: e7c2d9f4a108
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "aa042f33c911"
down_revision: Union[str, None] = "e7c2d9f4a108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("valid_role_fields", "users", type_="check")
    op.create_check_constraint(
        "valid_role_fields", "users",
        "(role IN ('admin', 'delivery_partner') AND username IS NOT NULL AND password_hash IS NOT NULL) OR (role = 'customer' AND email IS NOT NULL)",
    )
    op.create_table(
        "delivery_partner_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("employee_id", sa.String(50), nullable=False, unique=True),
        sa.Column("service_area", sa.String(150), nullable=True),
        sa.Column("service_pincodes", sa.JSON(), nullable=False),
        sa.Column("vehicle_type", sa.String(50), nullable=True),
        sa.Column("vehicle_registration", sa.String(30), nullable=True),
        sa.Column("max_active_deliveries", sa.Integer(), server_default="10", nullable=False),
        sa.Column("availability", sa.String(20), server_default="offline", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_active_deliveries > 0", name="ck_delivery_partner_capacity_positive"),
    )
    op.create_table(
        "delivery_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), server_default="assigned", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_delivery_assignment_version_positive"),
    )
    op.create_index("ix_delivery_assignments_partner_status", "delivery_assignments", ["partner_id", "status"])
    op.create_index("ix_delivery_assignments_order", "delivery_assignments", ["order_id", "assigned_at"])
    op.create_index("uq_delivery_active_assignment_order", "delivery_assignments", ["order_id"], unique=True,
        postgresql_where=sa.text("status IN ('assigned', 'accepted', 'picked_up', 'in_progress')"))
    op.create_table(
        "delivery_assignment_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_delivery_assignment_history_order", "delivery_assignment_history", ["order_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_delivery_assignment_history_order", table_name="delivery_assignment_history")
    op.drop_table("delivery_assignment_history")
    op.drop_index("uq_delivery_active_assignment_order", table_name="delivery_assignments")
    op.drop_index("ix_delivery_assignments_order", table_name="delivery_assignments")
    op.drop_index("ix_delivery_assignments_partner_status", table_name="delivery_assignments")
    op.drop_table("delivery_assignments")
    op.drop_table("delivery_partner_profiles")
    op.drop_constraint("valid_role_fields", "users", type_="check")
    op.create_check_constraint("valid_role_fields", "users",
        "(role = 'admin' AND username IS NOT NULL AND password_hash IS NOT NULL) OR (role = 'customer' AND email IS NOT NULL)")
