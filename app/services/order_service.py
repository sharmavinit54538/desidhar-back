import uuid
from datetime import datetime, timezone
from sqlalchemy import select, text, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.order import Order, OrderStatus, PaymentMethod, PaymentStatus
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.coupon_redemption import CouponRedemption
from app.services.checkout_service import evaluate_checkout
from app.services.stock_service import reserve_stock, release_stock
from app.services.order_transition import can_transition
from app.services.cart_service import clear_cart


async def generate_order_number(session: AsyncSession) -> str:
    res = await session.execute(text("SELECT nextval('order_number_seq')"))
    seq = res.scalar_one()
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"DD-{date_str}-{seq:06d}"


async def get_order_by_idempotency(session: AsyncSession, user_id: uuid.UUID, key: str) -> Order | None:
    stmt = select(Order).where(Order.user_id == user_id, Order.idempotency_key == key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def place_order(
    session: AsyncSession, user: User, address_id: uuid.UUID,
    method: str, idem_key: str, coupon_code: str | None = None, notes: str | None = None,
) -> tuple[Order | None, str | None]:
    existing = await get_order_by_idempotency(session, user.id, idem_key)
    if existing:
        return existing, None

    chk = await evaluate_checkout(session, user.id, address_id, coupon_code, method)
    if not chk.can_checkout or not chk.address:
        return None, "; ".join(chk.blocking_reasons)

    items_to_reserve = [(it["product_id"], it["quantity"]) for it in chk.items]
    ok, stock_err = await reserve_stock(session, items_to_reserve)
    if not ok:
        return None, stock_err or "Insufficient stock"

    ord_num = await generate_order_number(session)
    now = datetime.now(timezone.utc)
    init_status = OrderStatus.placed if method == PaymentMethod.cod.value else OrderStatus.payment_pending
    placed_at = now if init_status == OrderStatus.placed else None

    order = Order(
        order_number=ord_num, user_id=user.id, status=init_status,
        payment_method=PaymentMethod(method), payment_status=PaymentStatus.pending,
        shipping_name=chk.address.full_name, shipping_phone=chk.address.phone,
        shipping_line1=chk.address.line1, shipping_line2=chk.address.line2,
        shipping_landmark=chk.address.landmark, shipping_city=chk.address.city,
        shipping_state=chk.address.state, shipping_pincode=chk.address.pincode,
        subtotal_paise=chk.subtotal_paise, discount_paise=chk.discount_paise,
        coupon_code=chk.coupon_code, delivery_fee_paise=chk.delivery_fee_paise,
        total_paise=chk.total_paise, tax_paise=chk.total_tax_paise, notes=notes,
        idempotency_key=idem_key, placed_at=placed_at,
    )
    session.add(order)
    await session.flush()

    for it in chk.items:
        p = it["product"]
        oi = OrderItem(
            order_id=order.id, product_id=p.id, name_snapshot=p.name,
            pack_size_snapshot=p.pack_size, unit_snapshot=p.unit.value,
            quantity=it["quantity"], unit_price_paise=it["unit_price_paise"],
            unit_mrp_paise=it["unit_mrp_paise"], unit_cost_paise=p.cost_price_paise,
            gst_rate_percent=p.gst_rate_percent, discount_paise=it["discount_paise"],
            tax_paise=it["tax_paise"], line_total_paise=it["line_total_paise"],
        )
        session.add(oi)

    session.add(OrderStatusHistory(order_id=order.id, from_status=None, to_status=init_status.value, changed_by=user.id, note="Order created"))
    session.add(Payment(order_id=order.id, method=PaymentMethod(method), status=PaymentStatus.pending, amount_paise=order.total_paise))

    if chk.coupon:
        session.add(CouponRedemption(coupon_id=chk.coupon.id, user_id=user.id, order_id=order.id))

    await clear_cart(session, user.id)
    await session.flush()
    await session.refresh(order)
    return order, None


async def transition_order_status(
    session: AsyncSession, order: Order, target: str, changed_by: uuid.UUID | None = None,
    note: str | None = None, is_admin: bool = False,
) -> tuple[bool, str | None]:
    ok, err = can_transition(order.status.value, target, is_admin=is_admin)
    if not ok:
        return False, err

    prev = order.status.value
    order.status = OrderStatus(target)
    now = datetime.now(timezone.utc)
    if target == OrderStatus.confirmed.value:
        order.confirmed_at = now
    elif target == OrderStatus.delivered.value:
        order.delivered_at = now
        for p in order.payments:
            if p.method == PaymentMethod.cod and p.status == PaymentStatus.pending:
                p.status = PaymentStatus.paid
                p.paid_at = now
                order.payment_status = PaymentStatus.paid
    elif target == OrderStatus.cancelled.value:
        order.cancelled_at = now
        order.cancel_reason = note or "Cancelled"
        await release_stock(session, [(it.product_id, it.quantity) for it in order.items])

    session.add(OrderStatusHistory(order_id=order.id, from_status=prev, to_status=target, changed_by=changed_by, note=note))
    await session.flush()
    return True, None


async def get_user_order(session: AsyncSession, user_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    stmt = select(Order).where(Order.id == order_id, Order.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_user_orders(session: AsyncSession, user_id: uuid.UUID, page: int = 1, page_size: int = 20) -> tuple[list[Order], int]:
    stmt = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    count_stmt = select(func.count()).select_from(Order).where(Order.user_id == user_id)
    total = (await session.execute(count_stmt)).scalar() or 0
    items = list((await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all())
    return items, total


async def admin_list_orders(
    session: AsyncSession, status: str | None = None, method: str | None = None,
    pay_status: str | None = None, pincode: str | None = None, q: str | None = None,
    page: int = 1, page_size: int = 20,
) -> tuple[list[Order], int]:
    stmt = select(Order)
    count_stmt = select(func.count()).select_from(Order)
    if status:
        stmt = stmt.where(Order.status == OrderStatus(status))
        count_stmt = count_stmt.where(Order.status == OrderStatus(status))
    if method:
        stmt = stmt.where(Order.payment_method == PaymentMethod(method))
        count_stmt = count_stmt.where(Order.payment_method == PaymentMethod(method))
    if pay_status:
        stmt = stmt.where(Order.payment_status == PaymentStatus(pay_status))
        count_stmt = count_stmt.where(Order.payment_status == PaymentStatus(pay_status))
    if pincode:
        stmt = stmt.where(Order.shipping_pincode == pincode)
        count_stmt = count_stmt.where(Order.shipping_pincode == pincode)
    if q:
        pat = f"%{q.strip()}%"
        flt = or_(Order.order_number.ilike(pat), Order.shipping_name.ilike(pat), Order.shipping_phone.ilike(pat))
        stmt = stmt.where(flt)
        count_stmt = count_stmt.where(flt)

    total = (await session.execute(count_stmt)).scalar() or 0
    items = list((await session.execute(stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all())
    return items, total
