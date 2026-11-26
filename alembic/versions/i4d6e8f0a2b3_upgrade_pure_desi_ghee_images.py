"""Replace only Pure Desi Ghee image references with the ten-photo gallery.

Revision ID: i4d6e8f0a2b3
Revises: h3c5d7e9f1a2

No products, prices, stock, descriptions, or order snapshots are updated.
Deploy the accompanying static assets before running this data migration.
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "i4d6e8f0a2b3"
down_revision: Union[str, None] = "h3c5d7e9f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GHEE_IMAGES = tuple(
    f"/static/products/pure-desi-ghee/pure-desi-ghee-{index:02d}.webp"
    for index in range(1, 11)
)

PREVIOUS_IMAGES = (
    "/static/products/pure-desi-ghee/pure-desi-ghee-01-primary-white-1200.webp",
    "/static/products/pure-desi-ghee/pure-desi-ghee-02-spoon-drip-1200.webp",
    "/static/products/pure-desi-ghee/pure-desi-ghee-03-closeup-texture-1200.webp",
    "/static/products/pure-desi-ghee/pure-desi-ghee-04-traditional-bilona-1200.webp",
)


def _replace_images(conn: sa.Connection, urls: tuple[str, ...]) -> None:
    product_id = conn.execute(
        sa.text("SELECT id FROM products WHERE slug = :slug"),
        {"slug": "pure-desi-ghee"},
    ).scalar_one_or_none()
    if product_id is None:
        return

    existing = conn.execute(
        sa.text("SELECT url, sort_order FROM product_images WHERE product_id = :pid ORDER BY sort_order"),
        {"pid": product_id},
    ).all()
    if [(row[0], row[1]) for row in existing] == list(zip(urls, range(len(urls)))):
        return

    conn.execute(
        sa.text("DELETE FROM product_images WHERE product_id = :pid"),
        {"pid": product_id},
    )
    conn.execute(
        sa.text("INSERT INTO product_images (id, product_id, url, sort_order) VALUES (:id, :pid, :url, :sort_order)"),
        [
            {"id": str(uuid.uuid4()), "pid": product_id, "url": url, "sort_order": index}
            for index, url in enumerate(urls)
        ],
    )


def upgrade() -> None:
    _replace_images(op.get_bind(), GHEE_IMAGES)


def downgrade() -> None:
    _replace_images(op.get_bind(), PREVIOUS_IMAGES)
