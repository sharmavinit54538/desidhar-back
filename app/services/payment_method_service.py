from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.payment_method import PaymentMethodRecord
from app.models.pincode import Pincode
from app.schemas.payment_method import PaymentMethodOut

DEFAULT_METHODS = [
    {"id": "cod", "code": "cod", "name": "Cash on Delivery", "type": "cod", "enabled": True, "description": "Pay with cash upon delivery", "icon": "banknote", "min_order": 0, "max_order": 5000, "sort_order": 1},
    {"id": "upi", "code": "upi", "name": "UPI", "type": "online", "enabled": True, "description": "Google Pay, PhonePe, Paytm, BHIM", "icon": "smartphone", "min_order": 0, "max_order": None, "sort_order": 2},
    {"id": "card", "code": "card", "name": "Credit / Debit Card", "type": "online", "enabled": True, "description": "Visa, Mastercard, RuPay", "icon": "credit-card", "min_order": 0, "max_order": None, "sort_order": 3},
    {"id": "netbanking", "code": "netbanking", "name": "Net Banking", "type": "online", "enabled": True, "description": "All major Indian banks", "icon": "landmark", "min_order": 0, "max_order": None, "sort_order": 4},
]


async def seed_payment_methods(session: AsyncSession) -> None:
    for m in DEFAULT_METHODS:
        exists = (await session.execute(select(PaymentMethodRecord).where(PaymentMethodRecord.id == m["id"]))).scalar_one_or_none()
        if not exists:
            session.add(PaymentMethodRecord(**m))
    await session.flush()


async def list_payment_methods(
    session: AsyncSession,
    order_total: float | None = None,
    pincode: str | None = None,
    enabled_only: bool = True,
) -> list[PaymentMethodOut]:
    stmt = select(PaymentMethodRecord).order_by(PaymentMethodRecord.sort_order.asc())
    if enabled_only:
        stmt = stmt.where(PaymentMethodRecord.enabled.is_(True))
    records = list((await session.execute(stmt)).scalars().all())

    if not records:
        await seed_payment_methods(session)
        records = list((await session.execute(stmt)).scalars().all())

    cod_allowed = True
    if pincode:
        pin = (await session.execute(select(Pincode).where(Pincode.pincode == pincode.strip()))).scalar_one_or_none()
        if pin and (not pin.cod_available or not pin.is_serviceable):
            cod_allowed = False

    result: list[PaymentMethodOut] = []
    for r in records:
        if r.type == "cod" and not cod_allowed:
            continue
        if order_total is not None:
            if order_total < r.min_order:
                continue
            if r.max_order is not None and order_total > r.max_order:
                continue
        result.append(PaymentMethodOut(
            id=r.id, code=r.code, name=r.name, label=r.name,
            type=r.type, enabled=r.enabled, description=r.description,
            icon=r.icon, min_order=r.min_order, max_order=r.max_order,
            sort_order=r.sort_order,
        ))
    return result


async def update_payment_method(
    session: AsyncSession, method_id: str, data: dict,
) -> PaymentMethodRecord | None:
    stmt = select(PaymentMethodRecord).where((PaymentMethodRecord.id == method_id) | (PaymentMethodRecord.code == method_id))
    rec = (await session.execute(stmt)).scalar_one_or_none()
    if not rec:
        return None
    for k, v in data.items():
        if v is not None and hasattr(rec, k):
            setattr(rec, k, v)
    await session.flush()
    await session.refresh(rec)
    return rec
