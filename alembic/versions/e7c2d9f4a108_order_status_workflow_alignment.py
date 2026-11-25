"""Align order status fulfillment workflow and clean legacy pending records.

Revision ID: e7c2d9f4a108
Revises: c4d9e625ab71
Create Date: 2026-11-24 16:45:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e7c2d9f4a108"
down_revision: Union[str, None] = "c4d9e625ab71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Safely migrate any historical/legacy orders with status 'pending' to 'placed'
    # without touching 'payment_pending' which represents unconfirmed payment sessions.
    op.execute("""
        UPDATE orders
        SET status = 'placed',
            updated_at = NOW()
        WHERE status = 'pending';
    """)

    # 2. Update status history references from 'pending' to 'placed'
    op.execute("""
        UPDATE order_status_history
        SET from_status = 'placed'
        WHERE from_status = 'pending';
    """)
    op.execute("""
        UPDATE order_status_history
        SET to_status = 'placed'
        WHERE to_status = 'pending';
    """)

    # 3. Ensure column length on orders.status is at least 30 characters
    op.alter_column(
        "orders",
        "status",
        existing_type=sa.String(30),
        type_=sa.String(30),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Non-destructive: no-op since migrating 'pending' to 'placed' represents canonical state
    pass
