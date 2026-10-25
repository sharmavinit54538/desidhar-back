import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.delivery import ProductDeliveryConfigIn, ProductDeliveryConfigOut
from app.services.product_service import get_product_by_id
from app.services.product_delivery_service import get_product_delivery_config, set_product_delivery_config

router = APIRouter(prefix="/admin/products", tags=["admin-products"])


@router.get("/{product_id}/delivery", response_model=ProductDeliveryConfigOut)
async def get_delivery(product_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    prod = await get_product_by_id(db, product_id)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    mode, pins = await get_product_delivery_config(db, product_id)
    return ProductDeliveryConfigOut(product_id=product_id, delivery_mode=mode, pincodes=pins)


@router.put("/{product_id}/delivery", response_model=ProductDeliveryConfigOut)
async def update_delivery(
    product_id: uuid.UUID, data: ProductDeliveryConfigIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin),
):
    prod = await get_product_by_id(db, product_id)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if data.mode == "selected" and not data.pincodes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mode 'selected' requires at least one pincode")
    unknown = await set_product_delivery_config(db, prod, data.mode, data.pincodes)
    if unknown:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown pincodes: {', '.join(unknown)}")
    mode, pins = await get_product_delivery_config(db, product_id)
    return ProductDeliveryConfigOut(product_id=product_id, delivery_mode=mode, pincodes=pins)

