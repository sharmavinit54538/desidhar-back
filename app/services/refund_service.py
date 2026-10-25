import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.order import Order, PaymentStatus
from app.models.order_item import OrderItem
from app.models.refund import Refund, RefundReason


async def create_refund(
    session: AsyncSession, admin_id: uuid.UUID, order_id: uuid.UUID,
    item_id: uuid.UUID | None, amount_paise: int, reason: str, restock: bool, notes: str | None,
) -> tuple[Refund | None, str | None]:
    order = (await session.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        return None, "Order not found"
    existing_refunded = sum(r.amount_paise for r in order.refunds)
    if existing_refunded + amount_paise > order.total_paise:
        return None, f"Total refunded amount cannot exceed paid total of ₹{order.total_paise // 100}"

    if restock and item_id:
        it = (await session.execute(select(OrderItem).where(OrderItem.id == item_id, OrderItem.order_id == order_id))).scalar_one_or_none()
        if it:
            await session.execute(text("UPDATE products SET stock_qty = stock_qty + :q WHERE id = :id"), {"id": it.product_id, "q": it.quantity})

    ref = Refund(
        order_id=order_id, order_item_id=item_id, amount_paise=amount_paise,
        reason=RefundReason(reason), notes=notes, restock=restock, issued_by=admin_id,
    )
    session.add(ref)
    order.payment_status = PaymentStatus.refunded if (existing_refunded + amount_paise == order.total_paise) else PaymentStatus.partially_refunded
    await session.flush()
    return ref, None


async def list_order_refunds(session: AsyncSession, order_id: uuid.UUID) -> list[Refund]:
    return list((await session.execute(select(Refund).where(Refund.order_id == order_id).order_by(Refund.issued_at.desc()))).scalars().all())

