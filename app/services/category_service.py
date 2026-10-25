import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.category import Category
from app.services.slug_service import generate_unique_slug


async def list_active_categories(session: AsyncSession) -> list[Category]:
    result = await session.execute(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
    )
    return list(result.scalars().all())


async def list_all_categories(session: AsyncSession) -> list[Category]:
    result = await session.execute(select(Category).order_by(Category.sort_order))
    return list(result.scalars().all())


async def get_category_by_id(session: AsyncSession, category_id: uuid.UUID) -> Category | None:
    result = await session.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def create_category(session: AsyncSession, name: str, sort_order: int, is_active: bool) -> Category:
    slug = await generate_unique_slug(session, Category, name)
    cat = Category(name=name, slug=slug, sort_order=sort_order, is_active=is_active)
    session.add(cat)
    await session.flush()
    return cat


async def update_category(session: AsyncSession, cat: Category, data: dict) -> Category:
    if "name" in data and data["name"] is not None:
        cat.name = data["name"]
        cat.slug = await generate_unique_slug(session, Category, data["name"])
    if "sort_order" in data and data["sort_order"] is not None:
        cat.sort_order = data["sort_order"]
    if "is_active" in data and data["is_active"] is not None:
        cat.is_active = data["is_active"]
    await session.flush()
    return cat


async def category_has_products(session: AsyncSession, category_id: uuid.UUID) -> bool:
    from app.models.product import Product
    result = await session.execute(
        select(func.count()).select_from(Product).where(Product.category_id == category_id)
    )
    return result.scalar() > 0

