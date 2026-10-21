import re
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ConflictException,
)
from app.models.catalog import Category, Product, ProductImage, ProductStatus
from app.models.order import OrderItem
from app.schemas.catalog import (
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class CatalogService:

    # ------------------ CATEGORY METHODS ------------------

    @classmethod
    async def create_category(cls, db: AsyncSession, data: CategoryCreate) -> Category:
        slug = data.slug or slugify(data.name)
        existing = await db.execute(select(Category).where(Category.slug == slug))
        if existing.scalar_one_or_none():
            raise ConflictException(f"Category slug '{slug}' is already taken")

        if data.parent_id:
            parent = (await db.execute(select(Category).where(Category.id == data.parent_id))).scalar_one_or_none()
            if not parent:
                raise NotFoundException(f"Parent category with id {data.parent_id} not found")

        cat = Category(
            name=data.name,
            slug=slug,
            description=data.description,
            parent_id=data.parent_id,
            is_active=data.is_active,
        )
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        return cat

    @classmethod
    async def get_all_categories(cls, db: AsyncSession, only_active: bool = True) -> List[Category]:
        query = select(Category).order_by(Category.name)
        if only_active:
            query = query.where(Category.is_active.is_(True))
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def get_category_by_id(cls, db: AsyncSession, category_id: uuid.UUID) -> Category:
        result = await db.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()
        if not category:
            raise NotFoundException(f"Category with id {category_id} not found")
        return category

    # ------------------ PRODUCT METHODS ------------------

    @classmethod
    async def list_public_products(
        cls,
        db: AsyncSession,
        search: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        category_slug: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        in_stock_only: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> Tuple[List[Product], int]:
        """
        Public catalog query: Strict filtering for ACTIVE status and is_deleted=False.
        """
        filters = [
            Product.status == ProductStatus.ACTIVE,
            Product.is_deleted.is_(False),
        ]

        if search:
            s = f"%{search.strip()}%"
            filters.append(
                or_(
                    Product.name.ilike(s),
                    Product.description.ilike(s),
                    Product.sku.ilike(s),
                )
            )

        if category_id:
            filters.append(Product.category_id == category_id)
        elif category_slug:
            cat_query = select(Category.id).where(Category.slug == category_slug)
            found_cat_id = (await db.execute(cat_query)).scalar_one_or_none()
            if found_cat_id:
                filters.append(Product.category_id == found_cat_id)
            else:
                return [], 0

        if min_price is not None:
            filters.append(Product.base_price >= min_price)
        if max_price is not None:
            filters.append(Product.base_price <= max_price)
        if in_stock_only:
            filters.append(Product.stock > 0)

        # Count total
        count_stmt = select(func.count(Product.id)).where(and_(*filters))
        total = (await db.execute(count_stmt)).scalar() or 0

        # Query items with eager relationships
        offset = (page - 1) * size
        stmt = (
            select(Product)
            .where(and_(*filters))
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
            )
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await db.execute(stmt)
        products = list(result.scalars().all())

        return products, total

    @classmethod
    async def get_product_by_slug(cls, db: AsyncSession, slug: str) -> Product:
        query = (
            select(Product)
            .where(
                Product.slug == slug,
                Product.status == ProductStatus.ACTIVE,
                Product.is_deleted.is_(False),
            )
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
            )
        )
        result = await db.execute(query)
        product = result.scalar_one_or_none()
        if not product:
            raise NotFoundException(f"Product with slug '{slug}' not found")
        return product

    @classmethod
    async def get_product_by_id(cls, db: AsyncSession, product_id: uuid.UUID) -> Product:
        query = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
            )
        )
        result = await db.execute(query)
        product = result.scalar_one_or_none()
        if not product:
            raise NotFoundException(f"Product with id {product_id} not found")
        return product

    @classmethod
    async def create_product(
        cls,
        db: AsyncSession,
        data: ProductCreate,
        creator_id: uuid.UUID,
    ) -> Product:
        slug = data.slug or slugify(data.name)

        # Ensure slug uniqueness
        existing_slug = await db.execute(select(Product).where(Product.slug == slug))
        if existing_slug.scalar_one_or_none():
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # Ensure SKU uniqueness
        existing_sku = await db.execute(select(Product).where(Product.sku == data.sku.upper()))
        if existing_sku.scalar_one_or_none():
            raise ConflictException(f"Product SKU '{data.sku}' already exists")

        if data.category_id:
            cat = (await db.execute(select(Category).where(Category.id == data.category_id))).scalar_one_or_none()
            if not cat:
                raise NotFoundException(f"Category with id {data.category_id} not found")

        product = Product(
            name=data.name,
            slug=slug,
            description=data.description,
            base_price=data.base_price,
            sku=data.sku.upper(),
            stock=data.stock,
            status=data.status,
            is_deleted=False,
            category_id=data.category_id,
            created_by=creator_id,
        )
        db.add(product)
        await db.flush()

        for img in data.images:
            db.add(
                ProductImage(
                    product_id=product.id,
                    image_url=img.image_url,
                    alt_text=img.alt_text,
                    is_primary=img.is_primary,
                    sort_order=img.sort_order,
                )
            )

        await db.commit()
        return await cls.get_product_by_id(db, product.id)

    @classmethod
    async def update_product(
        cls,
        db: AsyncSession,
        product_id: uuid.UUID,
        data: ProductUpdate,
    ) -> Product:
        product = await cls.get_product_by_id(db, product_id)

        if data.name is not None:
            product.name = data.name
        if data.slug is not None:
            product.slug = data.slug
        if data.description is not None:
            product.description = data.description
        if data.base_price is not None:
            product.base_price = data.base_price
        if data.sku is not None:
            # Check SKU uniqueness if changed
            if data.sku.upper() != product.sku:
                existing_sku = await db.execute(select(Product).where(Product.sku == data.sku.upper()))
                if existing_sku.scalar_one_or_none():
                    raise ConflictException(f"Product SKU '{data.sku}' already in use")
                product.sku = data.sku.upper()
        if data.stock is not None:
            product.stock = data.stock
        if data.status is not None:
            product.status = data.status
        if data.category_id is not None:
            product.category_id = data.category_id

        if data.images is not None:
            # Replace images
            for old_img in product.images:
                await db.delete(old_img)
            for img in data.images:
                db.add(
                    ProductImage(
                        product_id=product.id,
                        image_url=img.image_url,
                        alt_text=img.alt_text,
                        is_primary=img.is_primary,
                        sort_order=img.sort_order,
                    )
                )

        await db.commit()
        return await cls.get_product_by_id(db, product.id)

    @classmethod
    async def archive_product(cls, db: AsyncSession, product_id: uuid.UUID) -> Product:
        """
        Safe Soft-Delete: Flags product as ARCHIVED and is_deleted=True.
        Prevents breaking historical orders and invoices.
        """
        product = await cls.get_product_by_id(db, product_id)
        product.status = ProductStatus.ARCHIVED
        product.is_deleted = True
        await db.commit()
        await db.refresh(product)
        return product

    @classmethod
    async def permanent_delete_product(cls, db: AsyncSession, product_id: uuid.UUID) -> None:
        """
        Permanent Hard-Delete: Strictly restricted to SUPER_ADMIN.
        Fails if product has been referenced in any historical order items.
        """
        product = await cls.get_product_by_id(db, product_id)

        # Check for past order items linked to this product
        order_count_query = select(func.count(OrderItem.id)).where(OrderItem.product_id == product_id)
        order_count = (await db.execute(order_count_query)).scalar() or 0

        if order_count > 0:
            raise BadRequestException(
                f"Cannot permanently delete product '{product.name}' (SKU: {product.sku}) because it is referenced in {order_count} historical order items. Use safe archive instead.",
                error_code="PRODUCT_LINKED_TO_ORDERS",
            )

        await db.delete(product)
        await db.commit()


catalog_service = CatalogService()
