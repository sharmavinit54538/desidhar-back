from __future__ import annotations

import html
import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_admin
from app.models.order import Order
from app.models.user import User

router = APIRouter(tags=["invoices"])


def _invoice(order: Order, copy_label: str) -> str:
    # Use only persisted order snapshots; invoice identity is deterministic and refresh-safe.
    date = order.placed_at or order.created_at
    date_text = date.astimezone(timezone.utc).strftime("%d %b %Y")
    items = "".join(
        "<tr><td>{}</td><td>{} {} {}</td><td>{}</td><td>₹{:.2f}</td><td>₹{:.2f}</td></tr>".format(
            html.escape(item.name_snapshot), item.pack_size_snapshot, html.escape(item.unit_snapshot),
            "", item.quantity, item.unit_price_paise / 100, item.line_total_paise / 100,
        ) for item in order.items
    )
    address = ", ".join(filter(None, [order.shipping_line1, order.shipping_line2, order.shipping_city, order.shipping_state, order.shipping_pincode]))
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Invoice {html.escape(order.order_number)}</title>
<style>body{{font:14px Arial,sans-serif;color:#222;margin:32px}}header{{display:flex;justify-content:space-between;border-bottom:2px solid #333;padding-bottom:12px}}table{{width:100%;border-collapse:collapse;margin-top:24px}}th,td{{padding:9px;border:1px solid #bbb;text-align:left}}.totals{{margin:22px 0 0 auto;width:280px}}.totals p{{display:flex;justify-content:space-between}}@media print{{button{{display:none}}body{{margin:16mm}}}}</style></head><body>
<button onclick='window.print()'>Print / Save PDF</button><header><div><h1>DesiDhar</h1><p>Order invoice</p></div><div><strong>{copy_label}</strong><p>Invoice: {html.escape(order.order_number)}</p><p>Date: {date_text}</p><p>Order ID: {html.escape(order.order_number)}</p></div></header>
<h3>Bill to</h3><p>{html.escape(order.shipping_name)} · {html.escape(order.shipping_phone)}<br>{html.escape(address)}</p>
<table><thead><tr><th>Item</th><th>Variant</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr></thead><tbody>{items}</tbody></table>
<div class='totals'><p><span>Subtotal</span><b>₹{order.subtotal_paise / 100:.2f}</b></p><p><span>Discount</span><b>−₹{order.discount_paise / 100:.2f}</b></p><p><span>Delivery</span><b>₹{order.delivery_fee_paise / 100:.2f}</b></p><p><span>Total</span><b>₹{order.total_paise / 100:.2f}</b></p><p><span>Payment</span><b>{html.escape(order.payment_status.value)}</b></p></div>
<p>Payment method: {html.escape(order.payment_method.value)}. This document reflects stored order details; tax registration information is not configured.</p></body></html>"""


async def _owned_order(order_id: uuid.UUID, user: User, db: AsyncSession) -> Order:
    order = (await db.execute(select(Order).where(Order.id == order_id, Order.user_id == user.id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return order


@router.get("/orders/{order_id}/invoice", response_class=HTMLResponse)
async def customer_invoice(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = await _owned_order(order_id, user, db)
    return HTMLResponse(_invoice(order, "CUSTOMER COPY"), headers={"Content-Disposition": f'inline; filename="invoice-{order.order_number}-customer.html"'})


@router.get("/admin/orders/{order_id}/invoice", response_class=HTMLResponse)
async def admin_invoice(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return HTMLResponse(_invoice(order, "ADMIN COPY"), headers={"Content-Disposition": f'inline; filename="invoice-{order.order_number}-admin.html"'})
