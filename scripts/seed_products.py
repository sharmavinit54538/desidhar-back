"""Idempotent seed script for categories and products."""
import asyncio
from decimal import Decimal
from sqlalchemy import select
from app.core.db import async_session_maker
from app.models.category import Category
from app.models.product import Product, UnitEnum
from app.models.product_image import ProductImage
from app.services.slug_service import generate_unique_slug

PRODUCT_IMAGE_MAP = {
    "Full Cream Milk": [
        {"url": "/static/products/product-milk.jpg", "sort_order": 0},
        {"url": "/static/products/product-photo-sheet.jpg", "sort_order": 1},
    ],
    "Toned Milk": [{"url": "/static/products/product-milk.jpg", "sort_order": 0}],
    "Cow Milk": [{"url": "/static/products/product-milk.jpg", "sort_order": 0}],
    "Pure Desi Ghee": [
        {"url": "/static/products/product-ghee.jpg", "sort_order": 0},
        {"url": "/static/products/story-churning.jpg", "sort_order": 1},
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
        {"url": "/static/products/product-dahi.jpg", "sort_order": 0},
        {"url": "/static/products/product-photo-sheet.jpg", "sort_order": 1},
    ],
    "Malai Paneer": [{"url": "/static/products/product-mava.jpg", "sort_order": 0}],
    "Fresh Cream": [{"url": "/static/products/product-dahi.jpg", "sort_order": 0}],
    "Rasgulla": [{"url": "/static/products/product-burfi.jpg", "sort_order": 0}],
    "Gulab Jamun": [
        {"url": "/static/products/product-milk-cake.jpg", "sort_order": 0},
        {"url": "/static/products/product-photo-sheet.jpg", "sort_order": 1},
    ],
    "Kaju Katli": [{"url": "/static/products/product-burfi.jpg", "sort_order": 0}],
}

CATEGORIES = [
    {"name": "Milk", "sort_order": 1},
    {"name": "Ghee and Butter", "sort_order": 2},
    {"name": "Paneer and Cream", "sort_order": 3},
    {"name": "Sweets", "sort_order": 4},
]

PRODUCTS = [
    {"category": "Milk", "name": "Full Cream Milk", "price_paise": 6800, "mrp_paise": 7000, "unit": "litre", "pack_size": 1, "stock_qty": 100, "shelf_life_days": 3, "description": "Farm-fresh full cream milk"},
    {"category": "Milk", "name": "Toned Milk", "price_paise": 5200, "mrp_paise": 5400, "unit": "litre", "pack_size": 1, "stock_qty": 80, "shelf_life_days": 3, "description": "Light and healthy toned milk"},
    {"category": "Milk", "name": "Cow Milk", "price_paise": 6000, "mrp_paise": 6200, "unit": "ml", "pack_size": 500, "stock_qty": 60, "shelf_life_days": 2, "description": "Pure desi cow milk"},
    {"category": "Ghee and Butter", "name": "Pure Desi Ghee", "price_paise": 59900, "mrp_paise": 62000, "unit": "kg", "pack_size": 1, "stock_qty": 40, "shelf_life_days": 180, "description": "Traditional bilona ghee made from cow milk"},
    {"category": "Ghee and Butter", "name": "Butter", "price_paise": 5600, "mrp_paise": 5700, "unit": "g", "pack_size": 500, "stock_qty": 50, "shelf_life_days": 90, "description": "Pasteurised salted table butter with a smooth, creamy texture"},
    {"category": "Ghee and Butter", "name": "White Butter (Makhan)", "price_paise": 3200, "mrp_paise": 3500, "unit": "g", "pack_size": 250, "stock_qty": 30, "shelf_life_days": 15, "description": "Homestyle white unsalted butter"},
    {"category": "Paneer and Cream", "name": "Fresh Paneer", "price_paise": 9800, "mrp_paise": 10000, "unit": "g", "pack_size": 500, "stock_qty": 25, "shelf_life_days": 5, "description": "Soft and fresh cottage cheese"},
    {"category": "Paneer and Cream", "name": "Malai Paneer", "price_paise": 12000, "mrp_paise": 12500, "unit": "g", "pack_size": 500, "stock_qty": 20, "shelf_life_days": 5, "description": "Premium creamy paneer"},
    {"category": "Paneer and Cream", "name": "Fresh Cream", "price_paise": 4500, "mrp_paise": 4800, "unit": "ml", "pack_size": 250, "stock_qty": 35, "shelf_life_days": 7, "description": "Rich whipping cream"},
    {"category": "Sweets", "name": "Rasgulla", "price_paise": 22000, "mrp_paise": 24000, "unit": "kg", "pack_size": 1, "stock_qty": 15, "shelf_life_days": 10, "description": "Spongy Bengali rasgulla in sugar syrup"},
    {"category": "Sweets", "name": "Gulab Jamun", "price_paise": 24000, "mrp_paise": 26000, "unit": "kg", "pack_size": 1, "stock_qty": 15, "shelf_life_days": 10, "description": "Soft khoya gulab jamun in rose syrup"},
    {"category": "Sweets", "name": "Kaju Katli", "price_paise": 85000, "mrp_paise": 90000, "unit": "g", "pack_size": 500, "stock_qty": 10, "shelf_life_days": 20, "description": "Premium cashew fudge barfi"},
]


async def seed() -> None:
    async with async_session_maker() as session:
        # Seed categories
        cat_map: dict[str, Category] = {}
        for c in CATEGORIES:
            result = await session.execute(select(Category).where(Category.name == c["name"]))
            existing = result.scalar_one_or_none()
            if existing:
                cat_map[c["name"]] = existing
                continue
            slug = await generate_unique_slug(session, Category, c["name"])
            cat = Category(name=c["name"], slug=slug, sort_order=c["sort_order"])
            session.add(cat)
            await session.flush()
            cat_map[c["name"]] = cat

        # Seed products
        for p in PRODUCTS:
            result = await session.execute(select(Product).where(Product.name == p["name"]))
            existing_prod = result.scalar_one_or_none()
            if existing_prod:
                if not existing_prod.images and p["name"] in PRODUCT_IMAGE_MAP:
                    for img in PRODUCT_IMAGE_MAP[p["name"]]:
                        session.add(ProductImage(product_id=existing_prod.id, url=img["url"], sort_order=img["sort_order"]))
                continue
            slug = await generate_unique_slug(session, Product, p["name"])
            product = Product(
                category_id=cat_map[p["category"]].id,
                name=p["name"],
                slug=slug,
                description=p.get("description"),
                price_paise=p["price_paise"],
                mrp_paise=p["mrp_paise"],
                unit=UnitEnum(p["unit"]),
                pack_size=Decimal(str(p["pack_size"])),
                stock_qty=p["stock_qty"],
                shelf_life_days=p.get("shelf_life_days"),
            )
            session.add(product)
            await session.flush()
            if p["name"] in PRODUCT_IMAGE_MAP:
                for img in PRODUCT_IMAGE_MAP[p["name"]]:
                    session.add(ProductImage(product_id=product.id, url=img["url"], sort_order=img["sort_order"]))

        await session.commit()
        print(f"Seeded {len(CATEGORIES)} categories and {len(PRODUCTS)} products")


if __name__ == "__main__":
    asyncio.run(seed())

