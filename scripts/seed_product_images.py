"""Seed and persist product images for all catalog products in PostgreSQL."""
import asyncio
from sqlalchemy import select
from app.core.db import async_session_maker
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.category import Category

PRODUCT_IMAGE_MAP = {
    "Full Cream Milk": [
        {"url": "/static/products/product-milk.jpg", "sort_order": 0},
        {"url": "/static/products/product-photo-sheet.jpg", "sort_order": 1},
    ],
    "Toned Milk": [
        {"url": "/static/products/product-milk.jpg", "sort_order": 0},
    ],
    "Cow Milk": [
        {"url": "/static/products/product-milk.jpg", "sort_order": 0},
    ],
    "Pure Desi Ghee": [
        {"url": "/static/products/product-ghee.jpg", "sort_order": 0},
        {"url": "/static/products/story-churning.jpg", "sort_order": 1},
    ],
    "Amul Butter": [
        {"url": "/static/products/product-ghee.jpg", "sort_order": 0},
    ],
    "White Butter (Makhan)": [
        {"url": "/static/products/product-ghee.jpg", "sort_order": 0},
    ],
    "Fresh Paneer": [
        {"url": "/static/products/product-dahi.jpg", "sort_order": 0},
        {"url": "/static/products/product-photo-sheet.jpg", "sort_order": 1},
    ],
    "Malai Paneer": [
        {"url": "/static/products/product-mava.jpg", "sort_order": 0},
    ],
    "Fresh Cream": [
        {"url": "/static/products/product-dahi.jpg", "sort_order": 0},
    ],
    "Rasgulla": [
        {"url": "/static/products/product-burfi.jpg", "sort_order": 0},
    ],
    "Gulab Jamun": [
        {"url": "/static/products/product-milk-cake.jpg", "sort_order": 0},
        {"url": "/static/products/product-photo-sheet.jpg", "sort_order": 1},
    ],
    "Kaju Katli": [
        {"url": "/static/products/product-burfi.jpg", "sort_order": 0},
    ],
}

CATEGORY_DEFAULT_IMAGE = {
    "Milk": "/static/products/product-milk.jpg",
    "Ghee and Butter": "/static/products/product-ghee.jpg",
    "Paneer and Cream": "/static/products/product-dahi.jpg",
    "Sweets": "/static/products/product-burfi.jpg",
}


async def seed_product_images() -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(Product))
        products = result.scalars().all()

        seeded_count = 0
        for product in products:
            # Check existing images
            existing_imgs = list(product.images)
            if existing_imgs:
                print(f"Product '{product.name}' already has {len(existing_imgs)} images, skipping.")
                continue

            target_images = PRODUCT_IMAGE_MAP.get(product.name)
            if not target_images:
                # Fallback to category default
                cat_result = await session.execute(select(Category).where(Category.id == product.category_id))
                cat = cat_result.scalar_one_or_none()
                cat_name = cat.name if cat else ""
                default_url = CATEGORY_DEFAULT_IMAGE.get(cat_name, "/static/products/product-milk.jpg")
                target_images = [{"url": default_url, "sort_order": 0}]

            for img_info in target_images:
                img_obj = ProductImage(
                    product_id=product.id,
                    url=img_info["url"],
                    sort_order=img_info["sort_order"],
                )
                session.add(img_obj)
                seeded_count += 1

            print(f"Added {len(target_images)} images for product '{product.name}'")

        await session.commit()
        print(f"Successfully seeded {seeded_count} product images into PostgreSQL.")


if __name__ == "__main__":
    asyncio.run(seed_product_images())
