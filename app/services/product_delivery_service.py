import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.models.pincode import Pincode
from app.models.product_pincode import ProductPincode
from app.models.delivery_mode import DeliveryMode


async def get_product_delivery_config(session: AsyncSession, product_id: uuid.UUID) -> tuple[str, list[str]]:
    prod = (await session.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not prod:
        return "", []
    q = select(Pincode.pincode).join(ProductPincode, Pincode.id == ProductPincode.pincode_id).where(ProductPincode.product_id == product_id).order_by(Pincode.pincode.asc())
    pins = list((await session.execute(q)).scalars().all())
    return prod.delivery_mode.value, pins


async def set_product_delivery_config(session: AsyncSession, prod: Product, mode: str, pins: list[str]) -> list[str]:
    clean_pins = list(dict.fromkeys(p.strip() for p in pins if p.strip()))
    found = list((await session.execute(select(Pincode).where(Pincode.pincode.in_(clean_pins)))).scalars().all()) if clean_pins else []
    unknown = [p for p in clean_pins if p not in {x.pincode for x in found}]
    if unknown:
        return unknown

    await session.execute(delete(ProductPincode).where(ProductPincode.product_id == prod.id))
    if mode == DeliveryMode.selected.value:
        for p in found:
            session.add(ProductPincode(product_id=prod.id, pincode_id=p.id))
    prod.delivery_mode = DeliveryMode(mode)
    await session.flush()
    return []

