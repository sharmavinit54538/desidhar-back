from __future__ import annotations

import html
import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.tokens import decode_token
from app.services.auth_service import get_user_by_id
from app.models.order import Order
from app.models.user import User

router = APIRouter(tags=["invoices"])


async def get_user_from_header_or_query(
    authorization: str | None = Header(default=None, alias="Authorization"),
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")

    try:
        payload = decode_token(raw_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def _invoice(order: Order, copy_label: str) -> str:
    # Use only persisted order snapshots; invoice identity is deterministic and refresh-safe.
    date = order.placed_at or order.created_at
    date_text = date.astimezone(timezone.utc).strftime("%d %b %Y, %I:%M %p")
    items_rows = "".join(
        "<tr><td><b>{}</b></td><td>{} {}</td><td style='text-align:center;'>{}</td><td style='text-align:right;'>₹{:.2f}</td><td style='text-align:right;'>₹{:.2f}</td></tr>".format(
            html.escape(item.name_snapshot),
            item.pack_size_snapshot,
            html.escape(item.unit_snapshot),
            item.quantity,
            item.unit_price_paise / 100,
            item.line_total_paise / 100,
        )
        for item in order.items
    )
    address_parts = [
        order.shipping_line1,
        order.shipping_line2,
        f"Landmark: {order.shipping_landmark}" if order.shipping_landmark else None,
        f"{order.shipping_city}, {order.shipping_state} {order.shipping_pincode}",
    ]
    address = "<br>".join(html.escape(p) for p in address_parts if p)

    tax_row = (
        f"<p><span>Taxes:</span><span>₹{order.tax_paise / 100:.2f}</span></p>"
        if order.tax_paise > 0
        else "<p><span>Taxes:</span><span>Included</span></p>"
    )

    delivery_row = (
        "FREE" if order.delivery_fee_paise == 0 else f"₹{order.delivery_fee_paise / 100:.2f}"
    )

    discount_row = (
        f"<p><span>Discount:</span><span>−₹{order.discount_paise / 100:.2f}</span></p>"
        if order.discount_paise > 0
        else ""
    )

    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Invoice {html.escape(order.order_number)} - DesiDhar</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937; margin: 32px; background: #fff; line-height: 1.5; }}
  .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #e5e7eb; padding-bottom: 16px; margin-bottom: 24px; }}
  .brand h1 {{ margin: 0; color: #111827; font-size: 26px; font-weight: 800; }}
  .brand p {{ margin: 4px 0 0; color: #6b7280; font-size: 14px; }}
  .meta {{ text-align: right; font-size: 13px; color: #374151; }}
  .meta strong {{ font-size: 15px; color: #111827; }}
  .section {{ margin-bottom: 20px; font-size: 14px; }}
  .section h3 {{ margin: 0 0 6px; font-size: 13px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 14px; }}
  th {{ background: #f9fafb; padding: 10px 12px; border: 1px solid #e5e7eb; text-align: left; font-weight: 600; color: #374151; }}
  td {{ padding: 10px 12px; border: 1px solid #e5e7eb; color: #374151; }}
  .totals {{ margin: 24px 0 0 auto; width: 320px; font-size: 14px; }}
  .totals p {{ display: flex; justify-content: space-between; margin: 6px 0; }}
  .totals .grand-total {{ border-top: 2px solid #111827; padding-top: 8px; font-size: 16px; font-weight: bold; color: #111827; }}
  .print-btn {{ background: #2874F0; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; cursor: pointer; font-weight: 600; margin-bottom: 20px; transition: background 0.2s; }}
  .print-btn:hover {{ background: #1a56b7; }}
  .footer {{ margin-top: 36px; padding-top: 12px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; text-align: center; }}
  @media print {{ .print-btn {{ display: none; }} body {{ margin: 12mm; }} }}
</style>
</head>
<body>
<button class='print-btn' onclick='window.print()'>Print / Save PDF</button>
<div class='header'>
  <div class='brand'>
    <h1>DesiDhar</h1>
    <p>Pure Dairy &amp; Traditional Sweets</p>
  </div>
  <div class='meta'>
    <div><strong>{copy_label}</strong></div>
    <div>Invoice No: <b>{html.escape(order.order_number)}</b></div>
    <div>Date: {date_text}</div>
    <div>Order Status: <span style="text-transform: capitalize;">{html.escape(order.status.value.replace('_', ' '))}</span></div>
  </div>
</div>

<div style='display: flex; justify-content: space-between; gap: 24px;' class='section'>
  <div>
    <h3>Delivery Address</h3>
    <p><b>{html.escape(order.shipping_name)}</b><br>{address}<br>Phone: {html.escape(order.shipping_phone)}</p>
  </div>
  <div style='text-align: right;'>
    <h3>Payment Details</h3>
    <p>Payment Method: <b style="text-transform: uppercase;">{html.escape(order.payment_method.value)}</b><br>
    Payment Status: <b style="text-transform: capitalize;">{html.escape(order.payment_status.value.replace('_', ' '))}</b></p>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th>Item Description</th>
      <th>Variant / Size</th>
      <th style='text-align: center;'>Qty</th>
      <th style='text-align: right;'>Unit Price</th>
      <th style='text-align: right;'>Amount</th>
    </tr>
  </thead>
  <tbody>
    {items_rows}
  </tbody>
</table>

<div class='totals'>
  <p><span>Subtotal:</span><span>₹{order.subtotal_paise / 100:.2f}</span></p>
  {discount_row}
  <p><span>Delivery:</span><span>{delivery_row}</span></p>
  {tax_row}
  <div class='grand-total'><p><span>Grand Total:</span><span>₹{order.total_paise / 100:.2f}</span></p></div>
</div>

<div class='footer'>
  <p>Thank you for shopping with DesiDhar! For customer support, visit your account's order section.</p>
</div>
</body></html>"""


async def _owned_order(order_id: uuid.UUID, user: User, db: AsyncSession) -> Order:
    order = (await db.execute(select(Order).where(Order.id == order_id, Order.user_id == user.id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return order


@router.get("/orders/{order_id}/invoice", response_class=HTMLResponse)
async def customer_invoice(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_user_from_header_or_query),
):
    order = await _owned_order(order_id, user, db)
    return HTMLResponse(
        _invoice(order, "CUSTOMER COPY"),
        headers={"Content-Disposition": f'inline; filename="invoice-{order.order_number}-customer.html"'},
    )


@router.get("/admin/orders/{order_id}/invoice", response_class=HTMLResponse)
async def admin_invoice(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return HTMLResponse(
        _invoice(order, "ADMIN COPY"),
        headers={"Content-Disposition": f'inline; filename="invoice-{order.order_number}-admin.html"'},
    )
