"""Idempotent seed script for delivery pincodes."""
import asyncio
from sqlalchemy import select
from app.core.db import async_session_maker
from app.models.pincode import Pincode

SAMPLE_PINCODES = [
    {
        "pincode": "500001", "area_name": "Abids", "city": "Hyderabad", "state": "Telangana",
        "is_serviceable": True, "delivery_fee_paise": 4000, "free_delivery_above_paise": 50000,
        "min_order_paise": 15000, "cod_available": True, "eta_hours": 12,
    },
    {
        "pincode": "500034", "area_name": "Banjara Hills", "city": "Hyderabad", "state": "Telangana",
        "is_serviceable": True, "delivery_fee_paise": 3000, "free_delivery_above_paise": 40000,
        "min_order_paise": 10000, "cod_available": True, "eta_hours": 8,
    },
    {
        "pincode": "500081", "area_name": "Madhapur", "city": "Hyderabad", "state": "Telangana",
        "is_serviceable": True, "delivery_fee_paise": 3500, "free_delivery_above_paise": 45000,
        "min_order_paise": 15000, "cod_available": True, "eta_hours": 10,
    },
    {
        "pincode": "560001", "area_name": "MG Road", "city": "Bengaluru", "state": "Karnataka",
        "is_serviceable": True, "delivery_fee_paise": 5000, "free_delivery_above_paise": 60000,
        "min_order_paise": 20000, "cod_available": True, "eta_hours": 24,
    },
    {
        "pincode": "560034", "area_name": "Koramangala", "city": "Bengaluru", "state": "Karnataka",
        "is_serviceable": True, "delivery_fee_paise": 4500, "free_delivery_above_paise": 50000,
        "min_order_paise": 15000, "cod_available": True, "eta_hours": 18,
    },
    {
        "pincode": "400001", "area_name": "Fort", "city": "Mumbai", "state": "Maharashtra",
        "is_serviceable": True, "delivery_fee_paise": 6000, "free_delivery_above_paise": 75000,
        "min_order_paise": 25000, "cod_available": True, "eta_hours": 24,
    },
    {
        "pincode": "400050", "area_name": "Bandra West", "city": "Mumbai", "state": "Maharashtra",
        "is_serviceable": True, "delivery_fee_paise": 5000, "free_delivery_above_paise": 70000,
        "min_order_paise": 20000, "cod_available": True, "eta_hours": 24,
    },
    {
        "pincode": "110001", "area_name": "Connaught Place", "city": "New Delhi", "state": "Delhi",
        "is_serviceable": True, "delivery_fee_paise": 5500, "free_delivery_above_paise": 60000,
        "min_order_paise": 20000, "cod_available": False, "eta_hours": 36,
    },
    {
        "pincode": "500099", "area_name": "Hyderabad Outskirts", "city": "Hyderabad", "state": "Telangana",
        "is_serviceable": False, "delivery_fee_paise": 0, "free_delivery_above_paise": None,
        "min_order_paise": 0, "cod_available": False, "eta_hours": None,
    },
    {
        "pincode": "400099", "area_name": "Mumbai Extended Zone", "city": "Mumbai", "state": "Maharashtra",
        "is_serviceable": False, "delivery_fee_paise": 0, "free_delivery_above_paise": None,
        "min_order_paise": 0, "cod_available": False, "eta_hours": None,
    },
    {
        "pincode": "110099", "area_name": "NCR Rural", "city": "New Delhi", "state": "Delhi",
        "is_serviceable": False, "delivery_fee_paise": 0, "free_delivery_above_paise": None,
        "min_order_paise": 0, "cod_available": False, "eta_hours": None,
    },
]


async def seed_pincodes() -> None:
    async with async_session_maker() as session:
        for p in SAMPLE_PINCODES:
            res = await session.execute(select(Pincode).where(Pincode.pincode == p["pincode"]))
            existing = res.scalar_one_or_none()
            if existing:
                for k, v in p.items():
                    setattr(existing, k, v)
            else:
                session.add(Pincode(**p))
        await session.commit()
        print(f"Seeded {len(SAMPLE_PINCODES)} sample pincodes successfully")


if __name__ == "__main__":
    asyncio.run(seed_pincodes())

