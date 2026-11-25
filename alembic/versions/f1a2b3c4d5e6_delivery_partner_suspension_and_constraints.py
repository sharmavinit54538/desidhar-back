"""Add delivery partner suspension, soft-delete, and assignment status constraints.

Revision ID: f1a2b3c4d5e6
Revises: d12a7f49c301
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d12a7f49c301"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "delivery_partner_profiles",
        sa.Column("is_suspended", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "delivery_partner_profiles",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_delivery_partner_availability",
        "delivery_partner_profiles",
        "availability IN ('available', 'offline')",
    )
    op.create_check_constraint(
        "ck_delivery_assignment_status",
        "delivery_assignments",
        "status IN ('assigned', 'accepted', 'picked_up', 'in_progress', 'completed', 'failed', 'rejected', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_delivery_assignment_status", "delivery_assignments", type_="check")
    op.drop_constraint("ck_delivery_partner_availability", "delivery_partner_profiles", type_="check")
    op.drop_column("delivery_partner_profiles", "deleted_at")
    op.drop_column("delivery_partner_profiles", "is_suspended")
