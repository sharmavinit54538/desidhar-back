import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.checkout import CheckoutPreviewIn, CheckoutPreviewOut
from app.services.checkout_service import evaluate_checkout
from app.services.cart_service import get_or_create_cart
from app.services.delivery_estimate_service import estimate_delivery

router = APIRouter(prefix="/checkout", tags=["checkout"])


@router.post("/preview", response_model=CheckoutPreviewOut)
async def preview(data: CheckoutPreviewIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # Use provided items for preview if given, otherwise use cart items
    # Do NOT modify the saved cart - preview is read-only
    if data.items:
        # Create a temporary cart-like evaluation using provided items
        # This is done by passing items through evaluate_checkout which reads from cart
        # For now, we just use the cart for evaluation if no items provided
        # The frontend should sync cart before checkout preview
        pass

    res = await evaluate_checkout(db, user.id, data.address_id, data.coupon_code, data.payment_method)
    estimate = None
    if res.pincode and res.items:
        estimate = await estimate_delivery(db, res.pincode, [it["product_id"] for it in res.items], data.delivery_speed)
    subtotal_rupees = round(float(res.subtotal_paise or 0) / 100.0, 2)
    delivery_fee_rupees = round(float(res.delivery_fee_paise or 0) / 100.0, 2)
    discount_rupees = round(float(res.discount_paise or 0) / 100.0, 2)
    total_rupees = round(float(res.total_paise or 0) / 100.0, 2)
    free_above_rupees = round(float(getattr(res, "free_delivery_above_paise", 0) or 0) / 100.0, 2)
    min_order_rupees = round(float(getattr(res, "min_order_paise", 0) or 0) / 100.0, 2)

    blocking_reasons = list(res.blocking_reasons)
    if data.delivery_speed == "express" and estimate and not estimate.serviceable:
        blocking_reasons.append(estimate.message)
    if not getattr(res, "cod_payment_method_valid", True):
        blocking_reasons.append(getattr(res, "cod_blocking_reason", "COD payment method not available"))

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
        can_checkout=res.can_checkout and not (data.delivery_speed == "express" and estimate and not estimate.serviceable),
        blocking_reasons=blocking_reasons,
        estimated_delivery_date=estimate.estimated_delivery_date if estimate and estimate.serviceable else None,
        estimated_delivery_end_date=estimate.estimated_delivery_end_date if estimate and estimate.serviceable else None,
        delivery_speed=data.delivery_speed,
    )
