from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.checkout import CheckoutPreviewIn, CheckoutPreviewOut
from app.services.checkout_service import evaluate_checkout

router = APIRouter(prefix="/checkout", tags=["checkout"])


@router.post("/preview", response_model=CheckoutPreviewOut)
async def preview(data: CheckoutPreviewIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    res = await evaluate_checkout(db, user.id, data.address_id, data.coupon_code, data.payment_method)
    return CheckoutPreviewOut(
        address_id=data.address_id, pincode=res.pincode, items=res.items, subtotal_paise=res.subtotal_paise,
        coupon_code=res.coupon_code, discount_paise=res.discount_paise, delivery_fee_paise=res.delivery_fee_paise,
        total_paise=res.total_paise, total_tax_paise=res.total_tax_paise, cod_available=res.cod_available,
        can_checkout=res.can_checkout, blocking_reasons=res.blocking_reasons,
    )

