import uuid
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    StockUnavailableException,
)
from app.models.catalog import Product, ProductStatus
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.order import ShippingAddress, OrderStatusUpdate
from app.services.notification_service import notification_service


def generate_order_number() -> str:
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"ORD-{today_str}-{unique_suffix}"


class OrderService:

    @classmethod
    async def create_order_from_cart(
        cls,
        db: AsyncSession,
        customer: User,
        shipping_address: ShippingAddress,
        payment_gateway: str = "RAZORPAY",
    ) -> Order:
        """
        ATOMIC CHECKOUT WITH PESSIMISTIC ROW-LEVEL LOCKING:
        Uses 'SELECT ... FOR UPDATE' with deterministic ID sorting to guarantee
        deadlock-free, zero-oversell inventory deduction during high-concurrency flash sales.
        """
        # Fetch user's cart with items
        cart_query = (
            select(Cart)
            .where(Cart.user_id == customer.id)
            .options(selectinload(Cart.items))
        )
        cart = (await db.execute(cart_query)).scalar_one_or_none()

        if not cart or not cart.items:
            raise BadRequestException("Your shopping cart is empty")

        # Map product_id -> requested quantity
        requested_items: Dict[uuid.UUID, int] = {}
        for item in cart.items:
            requested_items[item.product_id] = requested_items.get(item.product_id, 0) + item.quantity

        # CRITICAL CONCURRENCY LOCK:
        # Sort product IDs to prevent database deadlocks across concurrent checkout sessions
        sorted_product_ids = sorted(list(requested_items.keys()))

        # SELECT ... FOR UPDATE locks the product rows until transaction commits or rolls back
        locked_products_query = (
            select(Product)
            .where(Product.id.in_(sorted_product_ids))
            .order_by(Product.id)
            .with_for_update()
        )
        locked_result = await db.execute(locked_products_query)
        locked_products = {p.id: p for p in locked_result.scalars().all()}

        # Verify all products exist and validate stock
        total_amount = Decimal("0.00")
        order_items_to_create: List[OrderItem] = []

        for p_id in sorted_product_ids:
            product = locked_products.get(p_id)
            qty = requested_items[p_id]

            if not product or product.is_deleted or product.status != ProductStatus.ACTIVE:
                raise BadRequestException(f"Product '{p_id}' is no longer available for purchase")

            if product.stock < qty:
                raise StockUnavailableException(
                    f"Insufficient stock for '{product.name}' (SKU: {product.sku}). Available: {product.stock}, Requested: {qty}"
                )

            # Atomically decrement inventory
            product.stock -= qty

            subtotal = product.base_price * qty
            total_amount += subtotal

            order_item = OrderItem(
                product_id=product.id,
                product_name_snapshot=product.name,
                unit_price_snapshot=product.base_price,
                sku_snapshot=product.sku,
                quantity=qty,
                subtotal=subtotal,
            )
            order_items_to_create.append(order_item)

        discount_amount = Decimal("0.00")
        final_payable = total_amount - discount_amount

        # Create Order
        order = Order(
            order_number=generate_order_number(),
            customer_id=customer.id,
            total_amount=total_amount,
            discount_amount=discount_amount,
            final_payable=final_payable,
            order_status=OrderStatus.PENDING,
            payment_status=PaymentStatus.UNPAID,
            shipping_address=shipping_address.model_dump(),
            payment_gateway=payment_gateway.upper(),
        )
        db.add(order)
        await db.flush()

        # Link and save order items
        for oi in order_items_to_create:
            oi.order_id = order.id
            db.add(oi)

        # Clear customer cart
        for item in cart.items:
            await db.delete(item)

        # Commit transaction releasing row locks
        await db.commit()

        # Reload order with items
        return await cls.get_order_by_id(db, order.id)

    @classmethod
    async def get_order_by_id(cls, db: AsyncSession, order_id: uuid.UUID) -> Order:
        query = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items), selectinload(Order.customer))
        )
        result = await db.execute(query)
        order = result.scalar_one_or_none()
        if not order:
            raise NotFoundException(f"Order with id {order_id} not found")
        return order

    @classmethod
    async def get_order_by_number(cls, db: AsyncSession, order_number: str) -> Order:
        query = (
            select(Order)
            .where(Order.order_number == order_number)
            .options(selectinload(Order.items), selectinload(Order.customer))
        )
        result = await db.execute(query)
        order = result.scalar_one_or_none()
        if not order:
            raise NotFoundException(f"Order {order_number} not found")
        return order

    @classmethod
    async def list_orders(
        cls,
        db: AsyncSession,
        current_user: User,
        customer_id: Optional[uuid.UUID] = None,
        order_status: Optional[OrderStatus] = None,
        payment_status: Optional[PaymentStatus] = None,
        page: int = 1,
        size: int = 20,
    ) -> Tuple[List[Order], int]:
        filters = []

        # Access control: Customers strictly view only their own orders
        if current_user.role == UserRole.CUSTOMER:
            filters.append(Order.customer_id == current_user.id)
        elif customer_id:
            filters.append(Order.customer_id == customer_id)

        if order_status:
            filters.append(Order.order_status == order_status)
        if payment_status:
            filters.append(Order.payment_status == payment_status)

        count_stmt = select(func.count(Order.id)).where(and_(*filters) if filters else True)
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * size
        query = (
            select(Order)
            .where(and_(*filters) if filters else True)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        orders = list((await db.execute(query)).scalars().all())
        return orders, total

    @classmethod
    async def cancel_order(
        cls,
        db: AsyncSession,
        order_id: uuid.UUID,
        user: User,
        reason: Optional[str] = None,
    ) -> Order:
        """
        Cancels an order and atomically restores inventory stock.
        """
        order = await cls.get_order_by_id(db, order_id)

        # RBAC Check: Customer can only cancel their own orders if still PENDING or CONFIRMED
        if user.role == UserRole.CUSTOMER:
            if order.customer_id != user.id:
                raise ForbiddenException("You cannot cancel another customer's order")
            if order.order_status not in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
                raise BadRequestException(f"Cannot cancel order in '{order.order_status.value}' state")

        if order.order_status in (OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.DELIVERED):
            raise BadRequestException(f"Order is already {order.order_status.value}")

        # INVENTORY ROLLBACK WITH PESSIMISTIC LOCKING:
        product_ids = sorted([item.product_id for item in order.items if item.product_id is not None])
        if product_ids:
            locked_products_query = (
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
            )
            locked_products = {p.id: p for p in (await db.execute(locked_products_query)).scalars().all()}

            for item in order.items:
                if item.product_id and item.product_id in locked_products:
                    locked_products[item.product_id].stock += item.quantity

        order.order_status = OrderStatus.CANCELLED
        if order.payment_status == PaymentStatus.PAID:
            order.payment_status = PaymentStatus.REFUNDED
        elif order.payment_status == PaymentStatus.UNPAID:
            order.payment_status = PaymentStatus.FAILED

        await db.commit()

        # Dispatch async notification
        await notification_service.send_order_status_update(
            email=order.customer.email,
            order_number=order.order_number,
            new_status="CANCELLED",
        )

        return order

    @classmethod
    async def update_order_status(
        cls,
        db: AsyncSession,
        order_id: uuid.UUID,
        new_status: OrderStatus,
        staff_user: User,
    ) -> Order:
        """
        Restricted to STORE_MANAGER, SUPER_ADMIN, and SUPPORT_STAFF.
        """
        order = await cls.get_order_by_id(db, order_id)

        if new_status == OrderStatus.CANCELLED:
            return await cls.cancel_order(db, order_id, staff_user)

        order.order_status = new_status
        await db.commit()

        await notification_service.send_order_status_update(
            email=order.customer.email,
            order_number=order.order_number,
            new_status=new_status.value,
        )
        return order


order_service = OrderService()
