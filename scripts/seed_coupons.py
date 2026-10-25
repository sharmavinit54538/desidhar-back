"""Idempotent seed script for coupons."""
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.core.db import async_session_maker
from app.models.coupon import Coupon, CouponType

now = datetime.now(timezone.utc)
COUPONS = [
    {
        "code": "WELCOME10",
        "description": "10% off up to ₹100 on orders above ₹200",
        "type": CouponType.percent,
        "value": 10,
        "max_discount_paise": 10000,
        "min_order_paise": 20000,
        "starts_at": now - timedelta(days=30),
        "ends_at": now + timedelta(days=365),
        "usage_limit_total": 1000,
        "usage_limit_per_user": 1,
        "is_active": True,
    },
    {
        "code": "FLAT50",
        "description": "Flat ₹50 off on orders above ₹300",
        "type": CouponType.flat,
        "value": 5000,
        "max_discount_paise": None,
        "min_order_paise": 30000,
        "starts_at": now - timedelta(days=30),
        "ends_at": now + timedelta(days=365),
        "usage_limit_total": 500,
        "usage_limit_per_user": 3,
        "is_active": True,
    },
    {
        "code": "EXPIRED20",
        "description": "Expired promotional coupon",
        "type": CouponType.percent,
        "value": 20,
        "max_discount_paise": 20000,
        "min_order_paise": 10000,
        "starts_at": now - timedelta(days=120),
        "ends_at": now - timedelta(days=30),
        "usage_limit_total": 100,
        "usage_limit_per_user": 1,
        "is_active": True,
    },
]


async def seed() -> None:
    async with async_session_maker() as session:
        for data in COUPONS:
            res = await session.execute(select(Coupon).where(Coupon.code == data["code"]))
            c = res.scalar_one_or_none()
            if c:
                for k, v in data.items():
                    setattr(c, k, v)
            else:
                session.add(Coupon(**data))
        await session.commit()
        print(f"Seeded {len(COUPONS)} coupons successfully")


if __name__ == "__main__":
    asyncio.run(seed())

