"""Ghee image updates must preserve all product data and unrelated image rows."""
import importlib.util
from pathlib import Path
import uuid

import sqlalchemy as sa

from app.core.product_image_metadata import PURE_DESI_GHEE_IMAGES
from app.models.product_image import ProductImage
from app.schemas.product import ImageOut
from scripts.seed_products import PRODUCT_IMAGE_MAP as SEED_IMAGES
from scripts.seed_product_images import PRODUCT_IMAGE_MAP as SYNC_IMAGES


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "i4d6e8f0a2b3_upgrade_pure_desi_ghee_images.py"
    spec = importlib.util.spec_from_file_location("ghee_image_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ghee_migration_is_scoped_and_idempotent() -> None:
    migration = _migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE products (id TEXT PRIMARY KEY, slug TEXT, price_paise INTEGER, stock_qty INTEGER, description TEXT, sku TEXT)"))
        conn.execute(sa.text("CREATE TABLE product_images (id TEXT PRIMARY KEY, product_id TEXT, url TEXT, sort_order INTEGER)"))
        conn.execute(sa.text("INSERT INTO products VALUES ('ghee', 'pure-desi-ghee', 59900, 40, 'Existing description', 'EXISTING-SKU'), ('other', 'butter', 5600, 50, 'Unrelated description', 'OTHER-SKU')"))
        conn.execute(sa.text("INSERT INTO product_images VALUES ('old', 'ghee', '/old.webp', 0), ('keep', 'other', '/butter.webp', 0)"))
        products_before = conn.execute(sa.text("SELECT * FROM products ORDER BY id")).all()
        unrelated_before = conn.execute(sa.text("SELECT * FROM product_images WHERE product_id = 'other'")).all()

        migration._replace_images(conn, migration.GHEE_IMAGES)

        assert conn.execute(sa.text("SELECT * FROM products ORDER BY id")).all() == products_before
        assert conn.execute(sa.text("SELECT * FROM product_images WHERE product_id = 'other'")).all() == unrelated_before
        images_after = conn.execute(sa.text("SELECT * FROM product_images WHERE product_id = 'ghee' ORDER BY sort_order")).all()
        assert [(row.url, row.sort_order) for row in images_after] == [(image["url"], image["sort_order"]) for image in PURE_DESI_GHEE_IMAGES]

        migration._replace_images(conn, migration.GHEE_IMAGES)
        assert conn.execute(sa.text("SELECT * FROM product_images WHERE product_id = 'ghee' ORDER BY sort_order")).all() == images_after


def test_ghee_image_descriptions_and_seeders_agree() -> None:
    assert SEED_IMAGES["Pure Desi Ghee"] == SYNC_IMAGES["Pure Desi Ghee"] == list(PURE_DESI_GHEE_IMAGES)
    assert len({image["alt"] for image in PURE_DESI_GHEE_IMAGES}) == 10
    assert tuple(image["url"] for image in PURE_DESI_GHEE_IMAGES) == _migration().GHEE_IMAGES
    for entry in PURE_DESI_GHEE_IMAGES:
        image = ProductImage(id=uuid.uuid4(), product_id=uuid.uuid4(), url=entry["url"], sort_order=entry["sort_order"])
        assert ImageOut.model_validate(image).alt == entry["alt"]
        assert not any(claim in entry["alt"].lower() for claim in ("bilona", "grass-fed", "organic", "a2"))
