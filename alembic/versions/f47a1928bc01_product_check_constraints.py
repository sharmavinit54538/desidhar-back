"""add product check constraints

Revision ID: f47a1928bc01
Revises: d8e4c92a710f
Create Date: 2026-11-24 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f47a1928bc01'
down_revision: Union[str, None] = 'd8e4c92a710f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        'ck_cost_price_paise_non_negative',
        'products',
        'cost_price_paise >= 0'
    )
    op.create_check_constraint(
        'ck_gst_rate_percent_range',
        'products',
        'gst_rate_percent >= 0 AND gst_rate_percent <= 100'
    )
    op.create_check_constraint(
        'ck_max_qty_per_order_positive',
        'products',
        'max_qty_per_order > 0'
    )


def downgrade() -> None:
    op.drop_constraint('ck_max_qty_per_order_positive', 'products', type_='check')
    op.drop_constraint('ck_gst_rate_percent_range', 'products', type_='check')
    op.drop_constraint('ck_cost_price_paise_non_negative', 'products', type_='check')
