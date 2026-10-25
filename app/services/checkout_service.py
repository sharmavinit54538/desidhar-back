import uuid
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.cart import Cart
from app.models.address import Address
from app.models.coupon import Coupon
from app.models.pincode import Pincode
from app.services.delivery_service import check_deliverable
from app.services.coupon_service import validate_coupon_for_order
from app.services.discount_allocation import allocate_discount
from app.services.tax_service import compute_tax_paise


@dataclass
class EvaluatedCheckout:
    can_checkout: bool
    blocking_reasons: list[str]
    address: Address | None
    pincode: str
    items: list[dict]
    subtotal_paise: int
    coupon_code: str | None
    coupon: Coupon | None
    discount_paise: int
    delivery_fee_paise: int
    total_paise: int
    total_tax_paise: int
    cod_available: bool


async def evaluate_checkout(
    session: AsyncSession,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
    coupon_code: str | None = None,
    payment_method: str | None = None,
) -> EvaluatedCheckout:
    reasons: list[str] = []
    addr = (await session.execute(select(Address).where(Address.id == address_id, Address.user_id == user_id, Address.deleted_at.is_(None)))).scalar_one_or_none()
    if not addr:
        return EvaluatedCheckout(False, ["Address not found or has been deleted"], None, "", [], 0, None, None, 0, 0, 0, 0, False)

    cart = (await session.execute(select(Cart).where(Cart.user_id == user_id))).scalar_one_or_none()
    if not cart or not cart.items:
        return EvaluatedCheckout(False, ["Cart is empty"], addr, addr.pincode, [], 0, None, None, 0, 0, 0, 0, False)

    deliv_chk = await check_deliverable(session, addr.pincode, [it.product_id for it in cart.items])
    if not deliv_chk.pincode_serviceable:
        reasons.append(f"Pincode {addr.pincode} is not serviceable")

    subtotal = 0
    item_tuples = []
    for it in cart.items:
        p = it.product
        line = p.price_paise * it.quantity
        subtotal += line
        item_tuples.append((p.id, line))
        if not p.is_active:
            reasons.append(f"Product '{p.name}' is inactive")
        if it.quantity > p.stock_qty:
            reasons.append(f"Insufficient stock for '{p.name}' (available: {p.stock_qty})")
        if it.quantity > p.max_qty_per_order:
            reasons.append(f"Quantity for '{p.name}' exceeds limit of {p.max_qty_per_order}")
        is_deliv, d_reason = deliv_chk.results.get(p.id, (False, "Not deliverable"))
        if not is_deliv:
            reasons.append(f"'{p.name}' is not deliverable to {addr.pincode}: {d_reason}")

    pin_rec: Pincode | None = deliv_chk.pincode_record
    if pin_rec and subtotal < pin_rec.min_order_paise:
        reasons.append(f"Minimum order of ₹{pin_rec.min_order_paise // 100} required for {addr.pincode}")

    coupon, discount = None, 0
    if coupon_code:
        c, disc, err = await validate_coupon_for_order(session, coupon_code, user_id, subtotal)
        if err:
            reasons.append(err)
        else:
            coupon, discount = c, disc

    net_subtotal = max(0, subtotal - discount)
    del_fee = 0
    if pin_rec:
        if pin_rec.free_delivery_above_paise is not None and net_subtotal >= pin_rec.free_delivery_above_paise:
            del_fee = 0
        else:
            del_fee = pin_rec.delivery_fee_paise

    cod_avail = pin_rec.cod_available if pin_rec else False
    if payment_method == "cod" and not cod_avail:
        reasons.append(f"Cash on Delivery is unavailable for pincode {addr.pincode}")

    discounts = allocate_discount(item_tuples, discount)
    items_out = []
    total_tax = 0
    for it in cart.items:
        p = it.product
        line = p.price_paise * it.quantity
        item_disc = discounts.get(p.id, 0)
        line_after = line - item_disc
        tax = compute_tax_paise(line_after, p.gst_rate_percent)
        total_tax += tax
        is_deliv, d_reason = deliv_chk.results.get(p.id, (False, "Not deliverable"))
        items_out.append({
            "product_id": p.id, "name": p.name, "quantity": it.quantity, "unit_price_paise": p.price_paise,
            "unit_mrp_paise": p.mrp_paise, "line_subtotal_paise": line, "discount_paise": item_disc,
            "tax_paise": tax, "line_total_paise": line_after, "deliverable": is_deliv, "deliverability_reason": d_reason,
            "product": p,
        })

    total = subtotal - discount + del_fee
    return EvaluatedCheckout(
        can_checkout=len(reasons) == 0, blocking_reasons=reasons, address=addr, pincode=addr.pincode,
        items=items_out, subtotal_paise=subtotal, coupon_code=coupon.code if coupon else None, coupon=coupon,
        discount_paise=discount, delivery_fee_paise=del_fee, total_paise=total, total_tax_paise=total_tax,
        cod_available=cod_avail,
    )
