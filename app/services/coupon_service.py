import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.coupon import Coupon, CouponType
from app.models.coupon_redemption import CouponRedemption


async def get_coupon_by_code(session: AsyncSession, code: str) -> Coupon | None:
    return (await session.execute(select(Coupon).where(Coupon.code == code.strip().upper()))).scalar_one_or_none()


async def validate_coupon_for_order(
    session: AsyncSession, code: str, user_id: uuid.UUID, subtotal: int
) -> tuple[Coupon | None, int, str | None]:
    c = await get_coupon_by_code(session, code)
    if not c or not c.is_active:
        return None, 0, "Invalid or inactive coupon code"
    now = datetime.now(timezone.utc)
    if now < c.starts_at or now > c.ends_at:
        return None, 0, "Coupon has expired or is not yet active"
    if subtotal < c.min_order_paise:
        return None, 0, f"Minimum order of ₹{c.min_order_paise // 100} required for this coupon"

    if c.usage_limit_total is not None:
        total_used = (await session.execute(select(func.count()).select_from(CouponRedemption).where(CouponRedemption.coupon_id == c.id))).scalar() or 0
        if total_used >= c.usage_limit_total:
            return None, 0, "Coupon usage limit has been reached"

    if c.usage_limit_per_user is not None:
        user_used = (await session.execute(select(func.count()).select_from(CouponRedemption).where(CouponRedemption.coupon_id == c.id, CouponRedemption.user_id == user_id))).scalar() or 0
        if user_used >= c.usage_limit_per_user:
            return None, 0, "You have reached the redemption limit for this coupon"

    if c.type == CouponType.percent:
        disc = int(round((subtotal * c.value) / 100))
        if c.max_discount_paise is not None:
            disc = min(disc, c.max_discount_paise)
    else:
        disc = min(c.value, subtotal)
    return c, disc, None


async def list_coupons(session: AsyncSession) -> list[Coupon]:
    return list((await session.execute(select(Coupon).order_by(Coupon.created_at.desc()))).scalars().all())


async def create_coupon(session: AsyncSession, data: dict) -> Coupon:
    c = Coupon(**data)
    session.add(c)
    await session.flush()
    return c


async def update_coupon(session: AsyncSession, coupon: Coupon, data: dict) -> Coupon:
    for k, v in data.items():
        if v is not None:
            setattr(coupon, k, v)
    await session.flush()
    return coupon


async def delete_coupon(session: AsyncSession, coupon: Coupon) -> None:
    used = (await session.execute(select(func.count()).select_from(CouponRedemption).where(CouponRedemption.coupon_id == coupon.id))).scalar() or 0
    if used > 0:
        coupon.is_active = False
    else:
        await session.delete(coupon)
    await session.flush()

