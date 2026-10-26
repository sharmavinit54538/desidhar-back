from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.delivery import DeliveryCheckOut, ProductDeliveryCheckOut
from app.services.pincode_service import get_pincode_by_code
from app.services.delivery_service import check_deliverable
from app.services.product_service import get_product_by_slug

router = APIRouter(tags=["delivery"])


def format_delivery_response(p, pincode: str) -> DeliveryCheckOut:
    if not p or not p.is_serviceable:
        return DeliveryCheckOut(
            pincode=pincode,
            serviceable=False,
            message="Sorry, we don't deliver here yet" if p else "Pincode not serviceable",
            city=p.city if p else None,
            state=p.state if p else None,
            delivery_charge=0.0,
            free_delivery_above=0.0,
            min_order=0.0,
            cod_available=False,
            estimated_delivery=None,
        )

    del_charge = round(float(p.delivery_fee_paise or 0) / 100.0, 2)
    free_above = round(float(p.free_delivery_above_paise or 0) / 100.0, 2)
    min_ord = round(float(p.min_order_paise or 0) / 100.0, 2)
    eta_str = f"{p.eta_hours} hours" if p.eta_hours else "Tomorrow, 7-9 AM"

    return DeliveryCheckOut(
        pincode=p.pincode,
        serviceable=True,
        city=p.city,
        state=p.state,
        delivery_charge=del_charge,
        free_delivery_above=free_above,
        min_order=min_ord,
        estimated_delivery=eta_str,
        cod_available=p.cod_available,
        delivery_fee_paise=p.delivery_fee_paise,
        free_delivery_above_paise=p.free_delivery_above_paise,
        min_order_paise=p.min_order_paise,
        eta_hours=p.eta_hours,
        message="Delivery available in your area",
    )


@router.get("/delivery/check", response_model=DeliveryCheckOut)
async def check_pincode_query(
    pincode: str = Query(..., pattern=r"^[1-9][0-9]{5}$"),
    db: AsyncSession = Depends(get_db),
):
    p = await get_pincode_by_code(db, pincode)
    return format_delivery_response(p, pincode)


@router.get("/pincodes/check/{pincode}", response_model=DeliveryCheckOut)
async def check_pincode_path(
    pincode: str,
    db: AsyncSession = Depends(get_db),
):
    if not pincode.isdigit() or len(pincode) != 6 or pincode.startswith("0"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid 6-digit pincode")
    p = await get_pincode_by_code(db, pincode)
    return format_delivery_response(p, pincode)


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
