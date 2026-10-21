import asyncio
import logging
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
from app.models.catalog import Category, Product, ProductImage, ProductStatus

logger = logging.getLogger("desidhar.seed")


async def seed_initial_data(db: AsyncSession) -> None:
    # 1. Seed SUPER_ADMIN
    admin_query = select(User).where(User.role == UserRole.SUPER_ADMIN)
    existing_admin = (await db.execute(admin_query)).scalar_one_or_none()

    if not existing_admin:
        logger.info(f"Seeding default SUPER_ADMIN: {settings.FIRST_SUPER_ADMIN_EMAIL}")
        super_admin = User(
            email=settings.FIRST_SUPER_ADMIN_EMAIL.lower(),
            hashed_password=hash_password(settings.FIRST_SUPER_ADMIN_PASSWORD),
            first_name=settings.FIRST_SUPER_ADMIN_FIRST_NAME,
            last_name=settings.FIRST_SUPER_ADMIN_LAST_NAME,
            role=UserRole.SUPER_ADMIN,
            status=UserStatus.ACTIVE,
            permissions=[
                "product:write",
                "product:delete",
                "category:write",
                "order:refund",
                "order:process",
                "inventory:update",
                "staff:manage",
            ],
            is_verified=True,
        )
        db.add(super_admin)
        await db.commit()
        await db.refresh(super_admin)
        admin_id = super_admin.id
    else:
        admin_id = existing_admin.id

    # 2. Seed Default Categories if empty
    cat_query = select(Category)
    existing_cat = (await db.execute(cat_query)).first()

    if not existing_cat:
        logger.info("Seeding initial catalog categories...")
        categories_data = [
            Category(
                name="Heritage Kurtas",
                slug="heritage-kurtas",
                description="Fine handloom and hand-block printed cotton and silk kurtas.",
                is_active=True,
            ),
            Category(
                name="Handcrafted Sarees",
                slug="handcrafted-sarees",
                description="Authentic Chanderi, Banarasi, and Tussar silk sarees.",
                is_active=True,
            ),
            Category(
                name="Artisanal Accessories",
                slug="artisanal-accessories",
                description="Handcrafted leather juttis, dupattas, and brass jewelry.",
                is_active=True,
            ),
        ]
        db.add_all(categories_data)
        await db.commit()

        # Seed sample initial products
        p1 = Product(
            name="Royal Indigo Hand-Block Kurta",
            slug="royal-indigo-hand-block-kurta",
            description="Pure mulmul cotton kurta hand-printed using traditional Dabu mud-resist technique.",
            base_price=Decimal("2499.00"),
            sku="DSR-KRT-001",
            stock=45,
            status=ProductStatus.ACTIVE,
            category_id=categories_data[0].id,
            created_by=admin_id,
        )
        db.add(p1)
        await db.flush()

        db.add(
            ProductImage(
                product_id=p1.id,
                image_url="https://images.unsplash.com/photo-1597983073493-88cd35cf93b0?auto=format&fit=crop&w=800&q=80",
                alt_text="Royal Indigo Hand-Block Kurta Front View",
                is_primary=True,
                sort_order=0,
            )
        )

        p2 = Product(
            name="Varanasi Zari Mulberry Silk Saree",
            slug="varanasi-zari-mulberry-silk-saree",
            description="Woven on traditional pit-looms by master weavers with intricate antique gold zari borders.",
            base_price=Decimal("8999.00"),
            sku="DSR-SAR-002",
            stock=20,
            status=ProductStatus.ACTIVE,
            category_id=categories_data[1].id,
            created_by=admin_id,
        )
        db.add(p2)
        await db.flush()

        db.add(
            ProductImage(
                product_id=p2.id,
                image_url="https://images.unsplash.com/photo-1610030469983-98e550d6193c?auto=format&fit=crop&w=800&q=80",
                alt_text="Varanasi Zari Mulberry Silk Saree",
                is_primary=True,
                sort_order=0,
            )
        )

        await db.commit()
        logger.info("Sample products seeded successfully.")


async def run_cli_seed():
    logging.basicConfig(level=logging.INFO)
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
    print("Database seeding completed.")


if __name__ == "__main__":
    asyncio.run(run_cli_seed())
