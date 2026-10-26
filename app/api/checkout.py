import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.cart_item import CartItem
from app.schemas.checkout import CheckoutPreviewIn, CheckoutPreviewOut
from app.services.checkout_service import evaluate_checkout
from app.services.cart_service import get_or_create_cart

router = APIRouter(prefix="/checkout", tags=["checkout"])


@router.post("/preview", response_model=CheckoutPreviewOut)
async def preview(data: CheckoutPreviewIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if data.items:
        cart = await get_or_create_cart(db, user.id)
        await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        for it in data.items:
            prod_id = it.get("product_id")
            qty = int(it.get("quantity", 1))
            if prod_id and qty > 0:
                try:
                    p_uuid = uuid.UUID(str(prod_id))
                    db.add(CartItem(cart_id=cart.id, product_id=p_uuid, quantity=qty))
                except Exception:
                    pass
        await db.flush()

    res = await evaluate_checkout(db, user.id, data.address_id, data.coupon_code, data.payment_method)
    subtotal_rupees = round(float(res.subtotal_paise or 0) / 100.0, 2)
    delivery_fee_rupees = round(float(res.delivery_fee_paise or 0) / 100.0, 2)
    discount_rupees = round(float(res.discount_paise or 0) / 100.0, 2)
    total_rupees = round(float(res.total_paise or 0) / 100.0, 2)
    free_above_rupees = round(float(getattr(res, "free_delivery_above_paise", 0) or 0) / 100.0, 2)
    min_order_rupees = round(float(getattr(res, "min_order_paise", 0) or 0) / 100.0, 2)

    return CheckoutPreviewOut(
        address_id=data.address_id,
        pincode=res.pincode,
        items=res.items,
        subtotal=subtotal_rupees,
        delivery_fee=delivery_fee_rupees,
        delivery_charge=delivery_fee_rupees,
        discount=discount_rupees,
        total=total_rupees,
        free_delivery_above=free_above_rupees,
        min_order=min_order_rupees,
        subtotal_paise=res.subtotal_paise,
        coupon_code=res.coupon_code,
        discount_paise=res.discount_paise,
        delivery_fee_paise=res.delivery_fee_paise,
        total_paise=res.total_paise,
        total_tax_paise=res.total_tax_paise,
        cod_available=res.cod_available,
        can_checkout=res.can_checkout,
        blocking_reasons=res.blocking_reasons,
    )
