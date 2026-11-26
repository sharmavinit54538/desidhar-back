"""Seed and synchronize authentic product images for all catalog products in PostgreSQL."""
import asyncio
import sys
from sqlalchemy import delete, select
from app.core.db import async_session_maker
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.category import Category

PRODUCT_IMAGE_MAP = {
    "Full Cream Milk": [
        {"url": "/static/products/full-cream-milk/full-cream-milk-01-carafe-pour-1200.webp", "sort_order": 0},
        {"url": "/static/products/full-cream-milk/full-cream-milk-02-closeup-glass-1200.webp", "sort_order": 1},
    ],
    "Toned Milk": [
        {"url": "/static/products/toned-milk/toned-milk-01-tall-glass-1200.webp", "sort_order": 0},
        {"url": "/static/products/toned-milk/toned-milk-02-rim-closeup-1200.webp", "sort_order": 1},
    ],
    "Cow Milk": [
        {"url": "/static/products/cow-milk/cow-milk-01-studio-glass-1200.webp", "sort_order": 0},
        {"url": "/static/products/cow-milk/cow-milk-02-classic-glass-1200.webp", "sort_order": 1},
        {"url": "/static/products/cow-milk/cow-milk-03-rim-closeup-1200.webp", "sort_order": 2},
    ],
    "Pure Desi Ghee": [
        {"url": "/static/products/pure-desi-ghee/pure-desi-ghee-01-primary-white-1200.webp", "sort_order": 0},
        {"url": "/static/products/pure-desi-ghee/pure-desi-ghee-02-spoon-drip-1200.webp", "sort_order": 1},
        {"url": "/static/products/pure-desi-ghee/pure-desi-ghee-03-closeup-texture-1200.webp", "sort_order": 2},
        {"url": "/static/products/pure-desi-ghee/pure-desi-ghee-04-traditional-bilona-1200.webp", "sort_order": 3},
    ],
    "Butter": [
        {"url": "/static/products/butter/butter-01-primary-white-1200.webp", "sort_order": 0},
        {"url": "/static/products/butter/butter-02-lifestyle-1200.webp", "sort_order": 1},
        {"url": "/static/products/butter/butter-03-closeup-macro-1200.webp", "sort_order": 2},
        {"url": "/static/products/butter/butter-04-angle-1200.webp", "sort_order": 3},
        {"url": "/static/products/butter/butter-05-usage-1200.webp", "sort_order": 4},
    ],
    "White Butter (Makhan)": [
        {"url": "/static/products/white-butter-makhan/white-butter-makhan-01-ceramic-cream-studio-1600.webp", "sort_order": 0},
        {"url": "/static/products/white-butter-makhan/white-butter-makhan-02-terracotta-wooden-table-1600.webp", "sort_order": 1},
        {"url": "/static/products/white-butter-makhan/white-butter-makhan-03-creamy-texture-macro-1600.webp", "sort_order": 2},
        {"url": "/static/products/white-butter-makhan/white-butter-makhan-04-overhead-steel-bowl-1600.webp", "sort_order": 3},
        {"url": "/static/products/white-butter-makhan/white-butter-makhan-05-dark-slate-studio-1600.webp", "sort_order": 4},
        {"url": "/static/products/white-butter-makhan/white-butter-makhan-06-wooden-spoon-scoop-1600.webp", "sort_order": 5},
        {"url": "/static/products/white-butter-makhan/white-butter-makhan-07-handrolled-porcelain-bowl-1600.webp", "sort_order": 6},
    ],
    "Fresh Paneer": [
        {"url": "/static/products/fresh-paneer/fresh-paneer-01-plate-cubes-1200.webp", "sort_order": 0},
        {"url": "/static/products/fresh-paneer/fresh-paneer-02-diced-cubes-1200.webp", "sort_order": 1},
        {"url": "/static/products/fresh-paneer/fresh-paneer-03-closeup-texture-1200.webp", "sort_order": 2},
    ],
    "Malai Paneer": [
        {"url": "/static/products/malai-paneer/malai-paneer-01-artisan-slab-1200.webp", "sort_order": 0},
        {"url": "/static/products/malai-paneer/malai-paneer-02-cubes-and-cut-1200.webp", "sort_order": 1},
        {"url": "/static/products/malai-paneer/malai-paneer-03-closeup-texture-1200.webp", "sort_order": 2},
    ],
    "Fresh Cream": [
        {"url": "/static/products/fresh-cream/fresh-cream-01-ceramic-bowl-1200.webp", "sort_order": 0},
        {"url": "/static/products/fresh-cream/fresh-cream-02-closeup-swirl-1200.webp", "sort_order": 1},
    ],
    "Rasgulla": [
        {"url": "/static/products/rasgulla/rasgulla-01-primary-white-1200.webp", "sort_order": 0},
        {"url": "/static/products/rasgulla/rasgulla-02-lifestyle-1200.webp", "sort_order": 1},
        {"url": "/static/products/rasgulla/rasgulla-03-closeup-macro-1200.webp", "sort_order": 2},
        {"url": "/static/products/rasgulla/rasgulla-04-angle-1200.webp", "sort_order": 3},
    ],
    "Gulab Jamun": [
        {"url": "/static/products/gulab-jamun/gulab-jamun-01-primary-white-1200.webp", "sort_order": 0},
        {"url": "/static/products/gulab-jamun/gulab-jamun-02-lifestyle-1200.webp", "sort_order": 1},
        {"url": "/static/products/gulab-jamun/gulab-jamun-03-closeup-macro-1200.webp", "sort_order": 2},
        {"url": "/static/products/gulab-jamun/gulab-jamun-04-angle-1200.webp", "sort_order": 3},
        {"url": "/static/products/gulab-jamun/gulab-jamun-05-served-bowl-1200.webp", "sort_order": 4},
    ],
    "Kaju Katli": [
        {"url": "/static/products/kaju-katli/kaju-katli-01-primary-white-1200.webp", "sort_order": 0},
        {"url": "/static/products/kaju-katli/kaju-katli-02-lifestyle-1200.webp", "sort_order": 1},
        {"url": "/static/products/kaju-katli/kaju-katli-03-closeup-macro-1200.webp", "sort_order": 2},
        {"url": "/static/products/kaju-katli/kaju-katli-04-angle-1200.webp", "sort_order": 3},
    ],
}

CATEGORY_DEFAULT_IMAGE = {
    "Milk": "/static/products/full-cream-milk/full-cream-milk-01-carafe-pour-1200.webp",
    "Ghee and Butter": "/static/products/pure-desi-ghee/pure-desi-ghee-01-primary-white-1200.webp",
    "Paneer and Cream": "/static/products/fresh-paneer/fresh-paneer-01-plate-cubes-1200.webp",
    "Sweets": "/static/products/gulab-jamun/gulab-jamun-01-primary-white-1200.webp",
}


async def seed_product_images(*, force_sync: bool = False) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(Product).order_by(Product.name))
        products = result.scalars().all()

        seeded_count = 0
        for product in products:
            existing_imgs = list(product.images)
            if existing_imgs and not force_sync:
                print(f"Product '{product.name}' already has {len(existing_imgs)} images, skipping.")
                continue

            target_images = PRODUCT_IMAGE_MAP.get(product.name)
            if not target_images:
                if existing_imgs:
                    continue
                cat_result = await session.execute(select(Category).where(Category.id == product.category_id))
                cat = cat_result.scalar_one_or_none()
                cat_name = cat.name if cat else ""
                default_url = CATEGORY_DEFAULT_IMAGE.get(
                    cat_name,
                    "/static/products/full-cream-milk/full-cream-milk-01-carafe-pour-1200.webp",
                )
                target_images = [{"url": default_url, "sort_order": 0}]

            if existing_imgs:
                await session.execute(delete(ProductImage).where(ProductImage.product_id == product.id))

            for img_info in target_images:
                img_obj = ProductImage(
                    product_id=product.id,
                    url=img_info["url"],
                    sort_order=img_info["sort_order"],
                )
                session.add(img_obj)
                seeded_count += 1

            print(f"Synced {len(target_images)} images for product '{product.name}' ({product.slug})")

        await session.commit()
        print(f"Successfully persisted {seeded_count} product images into PostgreSQL.")


if __name__ == "__main__":
    sync_flag = "--sync" in sys.argv[1:]
    asyncio.run(seed_product_images(force_sync=sync_flag))
