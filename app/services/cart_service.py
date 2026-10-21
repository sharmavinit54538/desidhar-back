import uuid
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException, BadRequestException
from app.core.redis import RedisCartCache
from app.models.cart import Cart, CartItem
from app.models.catalog import Product, ProductStatus
from app.schemas.cart import CartResponse, CartItemResponse


class CartService:

    # ------------------ GUEST CART (REDIS) ------------------

    @classmethod
    async def get_guest_cart(cls, db: AsyncSession, session_id: str) -> CartResponse:
        raw_items = await RedisCartCache.get_cart(session_id)
        return await cls._build_cart_response_from_dict(db, raw_items)

    @classmethod
    async def add_to_guest_cart(
        cls,
        db: AsyncSession,
        session_id: str,
        product_id: uuid.UUID,
        quantity: int,
    ) -> CartResponse:
        product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
        if not product or product.is_deleted or product.status != ProductStatus.ACTIVE:
            raise NotFoundException("Product not found or currently unavailable")

        items = await RedisCartCache.get_cart(session_id)
        p_id_str = str(product_id)
        current_qty = items.get(p_id_str, 0)
        new_qty = current_qty + quantity

        if new_qty > product.stock:
            new_qty = product.stock
        if new_qty <= 0:
            items.pop(p_id_str, None)
        else:
            items[p_id_str] = new_qty

        await RedisCartCache.save_cart(session_id, items)
        return await cls._build_cart_response_from_dict(db, items)

    @classmethod
    async def update_guest_cart_item(
        cls,
        db: AsyncSession,
        session_id: str,
        product_id: uuid.UUID,
        quantity: int,
    ) -> CartResponse:
        product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
        if not product or product.is_deleted or product.status != ProductStatus.ACTIVE:
            raise NotFoundException("Product not found or unavailable")

        items = await RedisCartCache.get_cart(session_id)
        p_id_str = str(product_id)

        if quantity > product.stock:
            quantity = product.stock

        if quantity <= 0:
            items.pop(p_id_str, None)
        else:
            items[p_id_str] = quantity

        await RedisCartCache.save_cart(session_id, items)
        return await cls._build_cart_response_from_dict(db, items)

    @classmethod
    async def remove_guest_cart_item(
        cls,
        db: AsyncSession,
        session_id: str,
        product_id: uuid.UUID,
    ) -> CartResponse:
        items = await RedisCartCache.get_cart(session_id)
        items.pop(str(product_id), None)
        await RedisCartCache.save_cart(session_id, items)
        return await cls._build_cart_response_from_dict(db, items)

    # ------------------ AUTHENTICATED CART (DB) ------------------

    @classmethod
    async def get_or_create_user_cart(cls, db: AsyncSession, user_id: uuid.UUID) -> Cart:
        query = (
            select(Cart)
            .where(Cart.user_id == user_id)
            .options(
                selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.images)
            )
        )
        result = await db.execute(query)
        cart = result.scalar_one_or_none()

        if not cart:
            cart = Cart(user_id=user_id)
            db.add(cart)
            await db.commit()
            await db.refresh(cart)
            cart.items = []

        return cart

    @classmethod
    async def get_user_cart(cls, db: AsyncSession, user_id: uuid.UUID) -> CartResponse:
        cart = await cls.get_or_create_user_cart(db, user_id)
        return cls._build_cart_response_from_db(cart)

    @classmethod
    async def add_to_user_cart(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        quantity: int,
    ) -> CartResponse:
        product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
        if not product or product.is_deleted or product.status != ProductStatus.ACTIVE:
            raise NotFoundException("Product not found or unavailable")

        cart = await cls.get_or_create_user_cart(db, user_id)

        # Check if item exists in cart
        existing_item = next((item for item in cart.items if item.product_id == product_id), None)
        if existing_item:
            new_qty = existing_item.quantity + quantity
            if new_qty > product.stock:
                new_qty = product.stock
            existing_item.quantity = new_qty
        else:
            item_qty = min(quantity, product.stock)
            if item_qty < 1 and product.stock > 0:
                item_qty = 1
            new_item = CartItem(
                cart_id=cart.id,
                product_id=product_id,
                quantity=item_qty,
            )
            db.add(new_item)

        await db.commit()
        return await cls.get_user_cart(db, user_id)

    @classmethod
    async def update_user_cart_item(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        quantity: int,
    ) -> CartResponse:
        cart = await cls.get_or_create_user_cart(db, user_id)
        existing_item = next((item for item in cart.items if item.product_id == product_id), None)
        if not existing_item:
            raise NotFoundException("Product is not in your cart")

        product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
        if not product or product.is_deleted or product.status != ProductStatus.ACTIVE:
            await db.delete(existing_item)
            await db.commit()
            return await cls.get_user_cart(db, user_id)

        if quantity > product.stock:
            quantity = product.stock

        if quantity <= 0:
            await db.delete(existing_item)
        else:
            existing_item.quantity = quantity

        await db.commit()
        return await cls.get_user_cart(db, user_id)

    @classmethod
    async def remove_user_cart_item(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> CartResponse:
        cart = await cls.get_or_create_user_cart(db, user_id)
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if item:
            await db.delete(item)
            await db.commit()
        return await cls.get_user_cart(db, user_id)

    @classmethod
    async def clear_user_cart(cls, db: AsyncSession, user_id: uuid.UUID) -> None:
        cart = await cls.get_or_create_user_cart(db, user_id)
        for item in cart.items:
            await db.delete(item)
        await db.commit()

    # ------------------ AUTO-MERGE GUEST CART ------------------

    @classmethod
    async def merge_guest_cart_into_user_cart(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        guest_session_id: Optional[str],
    ) -> CartResponse:
        """
        Merges guest cart items into authenticated user cart without duplicate line items.
        Respects stock limits, then invalidates guest cart.
        """
        if not guest_session_id:
            return await cls.get_user_cart(db, user_id)

        guest_items = await RedisCartCache.get_cart(guest_session_id)
        if not guest_items:
            return await cls.get_user_cart(db, user_id)

        cart = await cls.get_or_create_user_cart(db, user_id)

        for p_id_str, guest_qty in guest_items.items():
            try:
                p_uuid = uuid.UUID(p_id_str)
            except ValueError:
                continue

            product = (await db.execute(select(Product).where(Product.id == p_uuid))).scalar_one_or_none()
            if not product or product.is_deleted or product.status != ProductStatus.ACTIVE or product.stock <= 0:
                continue

            existing_item = next((item for item in cart.items if item.product_id == p_uuid), None)
            if existing_item:
                total_qty = existing_item.quantity + guest_qty
                existing_item.quantity = min(total_qty, product.stock)
            else:
                db_item = CartItem(
                    cart_id=cart.id,
                    product_id=p_uuid,
                    quantity=min(guest_qty, product.stock),
                )
                db.add(db_item)

        await db.commit()
        # Clean up Redis guest cart
        await RedisCartCache.delete_cart(guest_session_id)

        return await cls.get_user_cart(db, user_id)

    # ------------------ HELPER BUILDERS ------------------

    @staticmethod
    def _build_cart_response_from_db(cart: Cart) -> CartResponse:
        items_resp: List[CartItemResponse] = []
        total_items = 0
        total_amount = Decimal("0.00")

        for item in cart.items:
            product = item.product
            if not product:
                continue

            in_stock = (product.stock >= item.quantity) and not product.is_deleted and product.status == ProductStatus.ACTIVE
            subtotal = product.base_price * item.quantity

            primary_img = next((img.image_url for img in product.images if img.is_primary), None)
            if not primary_img and product.images:
                primary_img = product.images[0].image_url

            items_resp.append(
                CartItemResponse(
                    id=item.id,
                    product_id=product.id,
                    product_name=product.name,
                    sku=product.sku,
                    unit_price=product.base_price,
                    quantity=item.quantity,
                    subtotal=subtotal,
                    in_stock=in_stock,
                    stock_available=product.stock,
                    image_url=primary_img,
                )
            )
            total_items += item.quantity
            total_amount += subtotal

        return CartResponse(
            id=cart.id,
            items=items_resp,
            total_items=total_items,
            total_amount=total_amount,
            currency="INR",
        )

    @classmethod
    async def _build_cart_response_from_dict(
        cls,
        db: AsyncSession,
        raw_dict: Dict[str, int],
    ) -> CartResponse:
        if not raw_dict:
            return CartResponse(id=None, items=[], total_items=0, total_amount=Decimal("0.00"), currency="INR")

        product_ids = []
        for k in raw_dict.keys():
            try:
                product_ids.append(uuid.UUID(k))
            except ValueError:
                pass

        if not product_ids:
            return CartResponse(id=None, items=[], total_items=0, total_amount=Decimal("0.00"), currency="INR")

        query = (
            select(Product)
            .where(Product.id.in_(product_ids))
            .options(selectinload(Product.images))
        )
        products = list((await db.execute(query)).scalars().all())
        prod_map = {p.id: p for p in products}

        items_resp: List[CartItemResponse] = []
        total_items = 0
        total_amount = Decimal("0.00")

        for p_id in product_ids:
            prod = prod_map.get(p_id)
            if not prod:
                continue
            qty = raw_dict.get(str(p_id), 1)
            in_stock = (prod.stock >= qty) and not prod.is_deleted and prod.status == ProductStatus.ACTIVE
            subtotal = prod.base_price * qty

            primary_img = next((img.image_url for img in prod.images if img.is_primary), None)
            if not primary_img and prod.images:
                primary_img = prod.images[0].image_url

            items_resp.append(
                CartItemResponse(
                    id=None,
                    product_id=prod.id,
                    product_name=prod.name,
                    sku=prod.sku,
                    unit_price=prod.base_price,
                    quantity=qty,
                    subtotal=subtotal,
                    in_stock=in_stock,
                    stock_available=prod.stock,
                    image_url=primary_img,
                )
            )
            total_items += qty
            total_amount += subtotal

        return CartResponse(
            id=None,
            items=items_resp,
            total_items=total_items,
            total_amount=total_amount,
            currency="INR",
        )


cart_service = CartService()
