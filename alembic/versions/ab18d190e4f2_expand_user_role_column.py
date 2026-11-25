"""Expand users.role storage for delivery_partner.

Revision ID: ab18d190e4f2
Revises: aa042f33c911
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "ab18d190e4f2"
down_revision: Union[str, None] = "aa042f33c911"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "role", existing_type=sa.String(8), type_=sa.String(30), existing_nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    partner_count = bind.execute(sa.text("SELECT count(*) FROM users WHERE role = 'delivery_partner'")).scalar_one()
    if partner_count:
        raise RuntimeError("Cannot shrink users.role while delivery partner accounts exist")
    op.alter_column("users", "role", existing_type=sa.String(30), type_=sa.String(8), existing_nullable=False)
