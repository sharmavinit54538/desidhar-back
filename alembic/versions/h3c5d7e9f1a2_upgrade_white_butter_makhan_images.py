"""Upgrade White Butter (Makhan) images to 1600px+ food photography WebP series.

Revision ID: h3c5d7e9f1a2
Revises: g2b4c6d8e0f1
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "h3c5d7e9f1a2"
down_revision: Union[str, None] = "g2b4c6d8e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAKHAN_IMAGES = [
    "/static/products/white-butter-makhan/white-butter-makhan-01-ceramic-cream-studio-1600.webp",
    "/static/products/white-butter-makhan/white-butter-makhan-02-terracotta-wooden-table-1600.webp",
    "/static/products/white-butter-makhan/white-butter-makhan-03-creamy-texture-macro-1600.webp",
    "/static/products/white-butter-makhan/white-butter-makhan-04-overhead-steel-bowl-1600.webp",
    "/static/products/white-butter-makhan/white-butter-makhan-05-dark-slate-studio-1600.webp",
    "/static/products/white-butter-makhan/white-butter-makhan-06-wooden-spoon-scoop-1600.webp",
    "/static/products/white-butter-makhan/white-butter-makhan-07-handrolled-porcelain-bowl-1600.webp",
]


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM products WHERE slug = 'white-butter-makhan' LIMIT 1")
    ).first()
    if row is None:
        return

    pid = row[0]
    existing = [
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT url FROM product_images WHERE product_id = :pid ORDER BY sort_order"
            ),
            {"pid": pid},
        ).all()
    ]
    if existing != MAKHAN_IMAGES:
        conn.execute(
            sa.text("DELETE FROM product_images WHERE product_id = :pid"),
            {"pid": pid},
        )
        for idx, url in enumerate(MAKHAN_IMAGES):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO product_images (id, product_id, url, sort_order)
                    VALUES (:id, :pid, :url, :sort_order)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": pid,
                    "url": url,
                    "sort_order": idx,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM products WHERE slug = 'white-butter-makhan' LIMIT 1")
    ).first()
    if row is None:
        return

    pid = row[0]
    previous = [
        "/static/products/white-butter-makhan/white-butter-makhan-01-porcelain-bowl-1200.webp",
        "/static/products/white-butter-makhan/white-butter-makhan-02-closeup-spheres-1200.webp",
        "/static/products/white-butter-makhan/white-butter-makhan-03-closeup-texture-1200.webp",
        "/static/products/white-butter-makhan/white-butter-makhan-04-bilona-churning-1200.webp",
    ]
    conn.execute(
        sa.text("DELETE FROM product_images WHERE product_id = :pid"),
        {"pid": pid},
    )
    for idx, url in enumerate(previous):
        conn.execute(
            sa.text(
                """
                INSERT INTO product_images (id, product_id, url, sort_order)
                VALUES (:id, :pid, :url, :sort_order)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": pid,
                "url": url,
                "sort_order": idx,
            },
        )
