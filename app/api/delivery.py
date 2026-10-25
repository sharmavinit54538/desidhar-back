from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.delivery import DeliveryCheckOut, ProductDeliveryCheckOut
from app.services.pincode_service import get_pincode_by_code
from app.services.delivery_service import check_deliverable
from app.services.product_service import get_product_by_slug

router = APIRouter(tags=["delivery"])


@router.get("/delivery/check", response_model=DeliveryCheckOut)
async def check_pincode_delivery(
    pincode: str = Query(..., pattern=r"^[1-9][0-9]{5}$"),
    db: AsyncSession = Depends(get_db),
):
    p = await get_pincode_by_code(db, pincode)
    if not p:
        return DeliveryCheckOut(pincode=pincode, serviceable=False, message="Pincode not serviceable")
    msg = "Delivery available" if p.is_serviceable else "Delivery not serviceable in this area"
    return DeliveryCheckOut(
        pincode=p.pincode, serviceable=p.is_serviceable, city=p.city, state=p.state,
        delivery_fee_paise=p.delivery_fee_paise, free_delivery_above_paise=p.free_delivery_above_paise,
        min_order_paise=p.min_order_paise, cod_available=p.cod_available, eta_hours=p.eta_hours,
        message=msg,
    )


@router.get("/products/{slug}/delivery", response_model=ProductDeliveryCheckOut)
async def check_product_delivery(
    slug: str,
    pincode: str = Query(..., pattern=r"^[1-9][0-9]{5}$"),
    db: AsyncSession = Depends(get_db),
):
    prod = await get_product_by_slug(db, slug, active_only=True)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    chk = await check_deliverable(db, pincode=pincode, product_ids=[prod.id])
    deliv, reason = chk.results.get(prod.id, (False, "Product not available in this area"))
    return ProductDeliveryCheckOut(product_id=prod.id, slug=prod.slug, pincode=pincode, deliverable=deliv, reason=reason)

