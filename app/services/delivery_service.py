import uuid
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pincode import Pincode
from app.models.product import Product
from app.models.product_pincode import ProductPincode
from app.models.delivery_mode import DeliveryMode


@dataclass
class DeliveryResult:
    pincode: str
    pincode_exists: bool
    pincode_serviceable: bool
    pincode_record: Pincode | None
    results: dict[uuid.UUID, tuple[bool, str | None]]


async def check_deliverable(
    session: AsyncSession, pincode: str, product_ids: list[uuid.UUID] | None = None
) -> DeliveryResult:
    code = pincode.strip()
    pincode_obj = (await session.execute(select(Pincode).where(Pincode.pincode == code))).scalar_one_or_none()
    if product_ids is None:
        product_ids = list((await session.execute(select(Product.id).where(Product.is_active.is_(True)))).scalars().all())

    if not pincode_obj or not pincode_obj.is_serviceable:
        return DeliveryResult(code, pincode_obj is not None, False, pincode_obj, {pid: (False, "pincode not serviceable") for pid in product_ids})

    products = (await session.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
    selected = [p.id for p in products if p.delivery_mode == DeliveryMode.selected]
    allowed = set()
    if selected:
        q = select(ProductPincode.product_id).where(ProductPincode.pincode_id == pincode_obj.id, ProductPincode.product_id.in_(selected))
        allowed = set((await session.execute(q)).scalars().all())

    res = {p.id: (True, None) if p.delivery_mode == DeliveryMode.all or p.id in allowed else (False, "product not available in this area") for p in products}
    return DeliveryResult(code, True, True, pincode_obj, res)

