"""Replace Amul Butter product record with Butter and update studio WebP images.

Revision ID: g2b4c6d8e0f1
Revises: f1a2b3c4d5e6
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "g2b4c6d8e0f1"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUTTER_DESCRIPTION = "Pasteurised salted table butter with a smooth, creamy texture"
BUTTER_IMAGES = [
    "/static/products/butter/butter-01-primary-white-1200.webp",
    "/static/products/butter/butter-02-lifestyle-1200.webp",
    "/static/products/butter/butter-03-closeup-macro-1200.webp",
    "/static/products/butter/butter-04-angle-1200.webp",
    "/static/products/butter/butter-05-usage-1200.webp",
]


def upgrade() -> None:
    conn = op.get_bind()

    butter_row = conn.execute(
        sa.text("SELECT id FROM products WHERE slug = 'butter' LIMIT 1")
    ).first()
    amul_row = conn.execute(
        sa.text("SELECT id FROM products WHERE slug = 'amul-butter' LIMIT 1")
    ).first()

    target_id = None
    if amul_row and not butter_row:
        target_id = amul_row[0]
        conn.execute(
            sa.text(
                """
                UPDATE products
                SET name = 'Butter',
                    slug = 'butter',
                    description = :description,
                    updated_at = NOW()
                WHERE id = :pid
                """
            ),
            {"pid": target_id, "description": BUTTER_DESCRIPTION},
        )
    elif butter_row:
        target_id = butter_row[0]

    if target_id is not None:
        existing_urls = [
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT url FROM product_images WHERE product_id = :pid ORDER BY sort_order"
                ),
                {"pid": target_id},
            ).all()
        ]
        if existing_urls != BUTTER_IMAGES:
            conn.execute(
                sa.text("DELETE FROM product_images WHERE product_id = :pid"),
                {"pid": target_id},
            )
            for idx, url in enumerate(BUTTER_IMAGES):
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO product_images (id, product_id, url, sort_order)
                        VALUES (:id, :pid, :url, :sort_order)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "pid": target_id,
                        "url": url,
                        "sort_order": idx,
                    },
                )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE products
            SET name = 'Amul Butter',
                slug = 'amul-butter',
                description = 'Pasteurised salted butter',
                updated_at = NOW()
            WHERE slug = 'butter'
            """
        )
    )
