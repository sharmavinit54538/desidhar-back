import uuid
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select, text, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.order import Order, OrderStatus, PaymentMethod, PaymentStatus
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.coupon_redemption import CouponRedemption
from app.models.delivery_management import DeliveryAssignment, DeliveryAssignmentHistory
from app.models.order_lifecycle import OrderNotification, OrderAuditLog
from app.services.checkout_service import evaluate_checkout
from app.services.stock_service import reserve_stock, release_stock
from app.services.order_transition import can_transition
from app.services.cart_service import clear_cart
from app.services.delivery_estimate_service import estimate_delivery


async def generate_order_number(session: AsyncSession) -> str:
    res = await session.execute(text("SELECT nextval('order_number_seq')"))
    seq = res.scalar_one()
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"DD-{date_str}-{seq:06d}"


def _quote_hash(chk) -> str:
    """Generate a stable hash of the checkout quote for binding placement to preview."""
    # Include all price-affecting fields
    quote_data = {
        "subtotal_paise": chk.subtotal_paise,
        "discount_paise": chk.discount_paise,
        "delivery_fee_paise": chk.delivery_fee_paise,
        "total_paise": chk.total_paise,
        "total_tax_paise": chk.total_tax_paise,
        "coupon_code": chk.coupon_code,
        "pincode": chk.pincode,
        "items": [(it["product_id"], it["quantity"], it["unit_price_paise"], it["line_total_paise"]) for it in chk.items],
    }
    return hashlib.sha256(json.dumps(quote_data, sort_keys=True, default=str).encode()).hexdigest()[:32]


async def get_order_by_idempotency(session: AsyncSession, user_id: uuid.UUID, key: str) -> Order | None:
    stmt = select(Order).where(Order.user_id == user_id, Order.idempotency_key == key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def place_order(
    session: AsyncSession, user: User, address_id: uuid.UUID,
    method: str, idem_key: str, coupon_code: str | None = None, notes: str | None = None,
    delivery_speed: str = "standard",
    quote_hash: str | None = None,
) -> tuple[Order | None, str | None, dict | None]:
    # Serialize checkout attempts per customer so the idempotency lookup and stock
    # reservation cannot race into duplicate orders.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = await get_order_by_idempotency(session, user.id, idem_key)
    if existing:
        return existing, None, None

    chk = await evaluate_checkout(session, user.id, address_id, coupon_code, method)
    if not chk.can_checkout or not chk.address:
        return None, "; ".join(chk.blocking_reasons), None

    # Verify quote hash if provided - if mismatched, return revised quote for confirmation
    if quote_hash:
        current_hash = _quote_hash(chk)
        if quote_hash != current_hash:
            # Return revised quote for frontend to show and ask for confirmation
            revised_quote = {
                "subtotal_paise": chk.subtotal_paise,
                "discount_paise": chk.discount_paise,
                "delivery_fee_paise": chk.delivery_fee_paise,
                "total_paise": chk.total_paise,
                "total_tax_paise": chk.total_tax_paise,
                "coupon_code": chk.coupon_code,
                "quote_hash": current_hash,
            }
            return None, "Quote has changed; please confirm revised amounts", revised_quote

    items_to_reserve = [(it["product_id"], it["quantity"]) for it in chk.items]
    estimate = await estimate_delivery(session, chk.pincode, [it["product_id"] for it in chk.items], delivery_speed)
    if not estimate.serviceable:
        return None, estimate.message, None
    ok, stock_err = await reserve_stock(session, items_to_reserve)
    if not ok:
        return None, stock_err or "Insufficient stock", None

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
        total_paise=chk.total_paise, tax_paise=chk.total_tax_paise, notes=notes, items=[], history=[],
        idempotency_key=idem_key, placed_at=placed_at, delivery_speed=delivery_speed,
        estimated_delivery_date=estimate.estimated_delivery_date,
        estimated_delivery_end_date=estimate.estimated_delivery_end_date,
    )
    session.add(order)
    await session.flush()

    for it in chk.items:
        p = it["product"]
        oi = OrderItem(
            order_id=order.id, product_id=p.id, name_snapshot=p.name,
            pack_size_snapshot=p.pack_size, unit_snapshot=p.unit.value,
            # This catalog has no SKU field/table; preserve null rather than inventing one.
            sku_snapshot=None,
            image_url_snapshot=(p.images[0].url if p.images else None),
            quantity=it["quantity"], unit_price_paise=it["unit_price_paise"],
            unit_mrp_paise=it["unit_mrp_paise"], unit_cost_paise=p.cost_price_paise,
            gst_rate_percent=p.gst_rate_percent, discount_paise=it["discount_paise"],
            tax_paise=it["tax_paise"], line_total_paise=it["line_total_paise"],
        )
        order.items.append(oi)

    order.history.append(OrderStatusHistory(order_id=order.id, from_status=None, to_status=init_status.value,
                                           changed_by=user.id, note="Order created", actor_type="customer",
                                           customer_visible_message="Order placed", event_source="checkout"))
    session.add(OrderNotification(order_id=order.id, user_id=user.id, event_type="order_status",
                                  event_key=f"status:1:{init_status.value}", channel="in_app", recipient=None,
                                  message=f"Order {init_status.value.replace('_', ' ')}", payload={"order_id": str(order.id), "status": init_status.value}, status="queued"))
    session.add(Payment(order_id=order.id, method=PaymentMethod(method), status=PaymentStatus.pending, amount_paise=order.total_paise))

    recipient = user.email
    if recipient:
        eta = order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else "to be confirmed"
        eta_end = f" to {order.estimated_delivery_end_date.isoformat()}" if order.estimated_delivery_end_date else ""
        message = f"Thank you for your order {order.order_number}. Expected delivery: {eta}{eta_end}. Track your order in My Orders."
        session.add(OrderNotification(order_id=order.id, user_id=user.id, event_type="order_confirmation",
                                      event_key="order-confirmation-email", channel="email", recipient=recipient,
                                      message=message, payload={"order_number": order.order_number,
                                      "estimated_delivery_date": eta, "estimated_delivery_end_date": order.estimated_delivery_end_date.isoformat() if order.estimated_delivery_end_date else None},
                                      status="queued"))

    if chk.coupon:
        session.add(CouponRedemption(coupon_id=chk.coupon.id, user_id=user.id, order_id=order.id))

    await clear_cart(session, user.id)
    await session.flush()
    await session.refresh(order)
    # Return order, error, and quote hash for frontend to store
    return order, None, {"quote_hash": _quote_hash(chk)}


async def transition_order_status(
    session: AsyncSession, order: Order, target: str, changed_by: uuid.UUID | None = None,
    note: str | None = None, is_admin: bool = False, expected_version: int | None = None,
    actor_type: str | None = None,
) -> tuple[bool, str | None]:
    # Serialize competing transitions and reject stale admin/customer forms.
    locked = (await session.execute(select(Order).where(Order.id == order.id).with_for_update())).scalar_one()
    if expected_version is not None and locked.version != expected_version:
        permitted = ", ".join(locked.allowed_next_statuses) or "none"
        return False, (
            f"Order status changed concurrently: current='{locked.status.value}', requested='{target}', "
            f"permitted next statuses: {permitted}. Refresh the order and try again."
        )
    order = locked
    ok, err = can_transition(order.status.value, target, is_admin=is_admin)
    if not ok:
        return False, err

    prev = order.status.value
    order.status = OrderStatus(target)
    now = datetime.now(timezone.utc)
    order.version += 1
    order.updated_at = now
    if target == OrderStatus.confirmed.value:
        order.confirmed_at = now
    elif target == OrderStatus.packed.value:
        order.packed_at = now
    elif target == OrderStatus.shipped.value:
        order.shipped_at = now
        if order.shipment:
            order.shipment.shipment_status = target
            order.shipment.shipped_at = now
    elif target == OrderStatus.out_for_delivery.value:
        order.out_for_delivery_at = now
        if order.shipment:
            order.shipment.shipment_status = target
    elif target == OrderStatus.delivered.value:
        order.delivered_at = now
        if order.shipment:
            order.shipment.shipment_status = target
            order.shipment.delivered_at = now
        # Fulfill Section 10: Fulfillment status remains separate from payment status.
        # Do not automatically mark COD as paid; payment must be separately verified.
    elif target == OrderStatus.cancelled.value:
        order.cancelled_at = now
        order.cancel_reason = note or "Cancelled"
        if order.stock_reserved and not order.stock_released:
            await release_stock(session, [(it.product_id, it.quantity) for it in order.items])
            order.stock_released = True
        # Cancel any active delivery assignment and free partner capacity
        from app.models.delivery_management import DeliveryAssignment
        ACTIVE_ASSIGNMENT_STATUSES = ("assigned", "accepted", "picked_up", "in_progress")
        active_assignment = (await session.execute(select(DeliveryAssignment).where(
            DeliveryAssignment.order_id == order.id,
            DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES)
        ).with_for_update())).scalar_one_or_none()
        if active_assignment:
            old_status = active_assignment.status
            active_assignment.status = "cancelled"
            active_assignment.version += 1
            active_assignment.updated_at = now
            session.add(DeliveryAssignmentHistory(
                assignment_id=active_assignment.id, order_id=order.id,
                actor_id=changed_by or order.user_id,
                from_status=old_status, to_status="cancelled",
                note=f"Order cancelled: {note or 'Cancelled'}"
            ))
            session.add(OrderNotification(
                order_id=order.id, user_id=active_assignment.partner_id,
                event_type="delivery_assignment",
                event_key=f"assignment:{active_assignment.id}:cancelled:{active_assignment.version}",
                channel="in_app", recipient=None,
                message=f"Delivery assignment for order {order.order_number} was cancelled",
                payload={"assignment_id": str(active_assignment.id), "order_id": str(order.id), "status": "cancelled"},
                status="queued"
            ))
    elif order.shipment:
        order.shipment.shipment_status = target

    visible = note if is_admin and note else f"Order {target.replace('_', ' ')}"
    resolved_actor = actor_type or ("admin" if is_admin else "customer")
    order.history.append(OrderStatusHistory(order_id=order.id, from_status=prev, to_status=target, changed_by=changed_by,
                                            note=note, actor_type=resolved_actor,
                                            reason=note, internal_admin_note=note if is_admin else None,
                                            customer_visible_message=visible, event_source="api"))
    event_key = f"status:{order.version}:{target}"
    session.add(OrderAuditLog(order_id=order.id, actor_id=changed_by,
                              actor_type=resolved_actor, action="status_change",
                              event_key=event_key, details={"from": prev, "to": target, "note": note}))
    session.add(OrderNotification(order_id=order.id, user_id=order.user_id, event_type="order_status",
                                  event_key=event_key, channel="in_app", recipient=None,
                                  message=visible, payload={"order_id": str(order.id), "status": target}, status="queued"))
    await session.flush()
    return True, None


async def get_user_order(session: AsyncSession, user_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id, Order.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_user_orders(session: AsyncSession, user_id: uuid.UUID, page: int = 1, page_size: int = 20) -> tuple[list[Order], int]:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .execution_options(populate_existing=True)
    )
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
        norm_status = status.strip().lower()
        if norm_status in OrderStatus._value2member_map_:
            order_enum = OrderStatus(norm_status)
            stmt = stmt.where(Order.status == order_enum)
            count_stmt = count_stmt.where(Order.status == order_enum)
    if method:
        norm_method = method.strip().lower()
        if norm_method in PaymentMethod._value2member_map_:
            stmt = stmt.where(Order.payment_method == PaymentMethod(norm_method))
            count_stmt = count_stmt.where(Order.payment_method == PaymentMethod(norm_method))
    if pay_status:
        norm_pay = pay_status.strip().lower()
        if norm_pay in PaymentStatus._value2member_map_:
            stmt = stmt.where(Order.payment_status == PaymentStatus(norm_pay))
            count_stmt = count_stmt.where(Order.payment_status == PaymentStatus(norm_pay))
    if pincode:
        stmt = stmt.where(Order.shipping_pincode == pincode)
        count_stmt = count_stmt.where(Order.shipping_pincode == pincode)
    if q:
        pat = f"%{q.strip()}%"
        flt = or_(Order.order_number.ilike(pat), Order.shipping_name.ilike(pat), Order.shipping_phone.ilike(pat))
        stmt = stmt.where(flt)
        count_stmt = count_stmt.where(flt)

    total = (await session.execute(count_stmt)).scalar() or 0
    items = list(
        (
            await session.execute(
                stmt.order_by(Order.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
    )
    return items, total
