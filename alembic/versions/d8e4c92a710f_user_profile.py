"""Persist customer profile name and mobile number.

Revision ID: d8e4c92a710f
Revises: c7a10243e8d1
"""
from alembic import op
import sqlalchemy as sa


revision = "d8e4c92a710f"
down_revision = "c7a10243e8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=15), nullable=True))
    # Safely backfill existing customer records from active default addresses
    op.execute("""
        UPDATE users u
        SET full_name = COALESCE(u.full_name, a.full_name),
            phone = COALESCE(u.phone, a.phone)
        FROM addresses a
        WHERE a.user_id = u.id AND a.is_default = true AND a.deleted_at IS NULL;
    """)


def downgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "full_name")
