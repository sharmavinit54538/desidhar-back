import uuid
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.category import Category
from app.services.slug_service import generate_unique_slug
from app.services.delivery_service import check_deliverable


async def create_product(session: AsyncSession, data: dict) -> Product:
    images_data = data.pop("images", [])
    slug = await generate_unique_slug(session, Product, data["name"])
    product = Product(slug=slug, **data)
    session.add(product)
    await session.flush()
    for img in images_data:
        session.add(ProductImage(product_id=product.id, url=img["url"], sort_order=img.get("sort_order", 0)))
    await session.flush()
    await session.refresh(product)
    return product


async def update_product(session: AsyncSession, product: Product, data: dict) -> Product:
    images_data = data.pop("images", None)
    if "name" in data and data["name"] is not None:
        product.slug = await generate_unique_slug(session, Product, data["name"])
    for key, value in data.items():
        if value is not None:
            setattr(product, key, value)
    if images_data is not None:
        for img in list(product.images):
            await session.delete(img)
        await session.flush()
        for img in images_data:
            session.add(ProductImage(product_id=product.id, url=img["url"], sort_order=img.get("sort_order", 0)))
    await session.flush()
    await session.refresh(product)
    return product


async def get_product_by_id(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    result = await session.execute(select(Product).where(Product.id == product_id))
    return result.scalar_one_or_none()


async def get_product_by_slug(session: AsyncSession, slug: str, active_only: bool = True) -> Product | None:
    stmt = select(Product).where(Product.slug == slug)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_products(
    session: AsyncSession,
    q: str | None = None,
    category_slug: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    in_stock: bool | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 20,
    active_only: bool = True,
    pincode: str | None = None,
) -> tuple[list[Product], int, bool | None]:
    stmt = select(Product)
    count_stmt = select(func.count()).select_from(Product)

    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
        count_stmt = count_stmt.where(Product.is_active.is_(True))

    pincode_serviceable: bool | None = None
    if pincode is not None:
        chk = await check_deliverable(session, pincode=pincode, product_ids=None)
        pincode_serviceable = chk.pincode_serviceable
        if not chk.pincode_serviceable:
            return [], 0, False
        deliv_ids = [pid for pid, (is_deliv, _) in chk.results.items() if is_deliv]
        stmt = stmt.where(Product.id.in_(deliv_ids))
        count_stmt = count_stmt.where(Product.id.in_(deliv_ids))

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(Product.name.ilike(pattern))
        count_stmt = count_stmt.where(Product.name.ilike(pattern))

    if category_slug:
        cat_sub = select(Category.id).where(Category.slug == category_slug).scalar_subquery()
        stmt = stmt.where(Product.category_id == cat_sub)
        count_stmt = count_stmt.where(Product.category_id == cat_sub)

    if min_price is not None:
        stmt = stmt.where(Product.price_paise >= min_price)
        count_stmt = count_stmt.where(Product.price_paise >= min_price)

    if max_price is not None:
        stmt = stmt.where(Product.price_paise <= max_price)
        count_stmt = count_stmt.where(Product.price_paise <= max_price)

    if in_stock is not None:
        if in_stock:
            stmt = stmt.where(Product.stock_qty > 0)
            count_stmt = count_stmt.where(Product.stock_qty > 0)
        else:
            stmt = stmt.where(Product.stock_qty == 0)
            count_stmt = count_stmt.where(Product.stock_qty == 0)

    order_map = {
        "newest": Product.created_at.desc(),
        "price_asc": Product.price_paise.asc(),
        "price_desc": Product.price_paise.desc(),
        "name": Product.name.asc(),
    }
    stmt = stmt.order_by(order_map.get(sort, Product.created_at.desc()))

    total = (await session.execute(count_stmt)).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    return list(result.scalars().all()), total, pincode_serviceable

