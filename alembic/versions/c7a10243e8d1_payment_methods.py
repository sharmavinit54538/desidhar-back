"""payment_methods

Revision ID: c7a10243e8d1
Revises: 507c90bd6952
Create Date: 2026-10-26 12:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c7a10243e8d1'
down_revision: Union[str, None] = '507c90bd6952'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('icon', sa.String(length=100), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('min_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # Seed default payment methods
    op.execute("""
        INSERT INTO payment_methods (id, code, name, type, enabled, description, icon, sort_order, min_order, max_order)
        VALUES
        ('cod', 'cod', 'Cash on Delivery', 'cod', true, 'Pay with cash upon delivery', 'banknote', 1, 0, 5000),
        ('upi', 'upi', 'UPI', 'online', true, 'Google Pay, PhonePe, Paytm, BHIM', 'smartphone', 2, 0, null),
        ('card', 'card', 'Credit / Debit Card', 'online', true, 'Visa, Mastercard, RuPay', 'credit-card', 3, 0, null),
        ('netbanking', 'netbanking', 'Net Banking', 'online', true, 'All major Indian banks', 'landmark', 4, 0, null)
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table('payment_methods')
