from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.payment import Payment
from app.models.order_status_history import OrderStatusHistory
from app.services.payments.mock_provider import MockPaymentProvider
from app.services.stock_service import release_stock

provider = MockPaymentProvider()


async def initiate_payment(session: AsyncSession, order: Order) -> dict:
    res = await provider.create_order(order.total_paise, order.order_number)
    pm = (await session.execute(select(Payment).where(Payment.order_id == order.id))).scalars().first()
    if pm:
        pm.provider = "mock"
        pm.provider_order_id = res["provider_order_id"]
    await session.flush()
    return {**res, "order_id": order.id, "order_number": order.order_number}


async def confirm_payment_success(session: AsyncSession, p_order_id: str, p_pay_id: str) -> Order | None:
    if not p_order_id:
        return None
    pm = (await session.execute(select(Payment).where(Payment.provider_order_id == p_order_id))).scalars().first()
    if not pm:
        return None
    order = (await session.execute(select(Order).where(Order.id == pm.order_id))).scalar_one()
    if pm.status == PaymentStatus.paid:
        return order

    pm.status = PaymentStatus.paid
    pm.provider_payment_id = p_pay_id
    pm.paid_at = datetime.now(timezone.utc)
    if order.status == OrderStatus.payment_pending:
        order.status = OrderStatus.placed
        order.placed_at = datetime.now(timezone.utc)
        session.add(OrderStatusHistory(order_id=order.id, from_status=OrderStatus.payment_pending.value, to_status=OrderStatus.placed.value, note="Payment successful"))
    await session.flush()
    return order


async def verify_payment(session: AsyncSession, payload: dict) -> tuple[bool, Order | None]:
    if not await provider.verify_payment(payload):
        return False, None
    order = await confirm_payment_success(session, payload.get("provider_order_id", ""), payload.get("provider_payment_id", "mock_pay"))
    return True, order


async def process_webhook(session: AsyncSession, payload: dict, sig: str) -> tuple[bool, Order | None]:
    valid, p_ord, p_pay, _ = await provider.parse_webhook(payload, sig)
    if not valid:
        return False, None
    order = await confirm_payment_success(session, p_ord, p_pay)
    return True, order


async def cancel_expired_unpaid_orders(session: AsyncSession, timeout_minutes: int = 30) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    stmt = select(Order).where(Order.status == OrderStatus.payment_pending, Order.created_at <= cutoff)
    orders = (await session.execute(stmt)).scalars().all()
    count = 0
    for o in orders:
        o.status = OrderStatus.cancelled
        o.cancelled_at = datetime.now(timezone.utc)
        o.cancel_reason = "Payment timeout"
        session.add(OrderStatusHistory(order_id=o.id, from_status=OrderStatus.payment_pending.value, to_status=OrderStatus.cancelled.value, note="Cancelled due to payment timeout"))
        await release_stock(session, [(it.product_id, it.quantity) for it in o.items])
        count += 1
    await session.flush()
    return count
