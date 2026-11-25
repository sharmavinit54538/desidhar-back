from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pincode import Pincode
from app.models.product import Product
from app.models.shipping_rule import ShippingRule

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class DeliveryEstimate:
    serviceable: bool
    pincode: str
    city: str | None
    state: str | None
    delivery_speed: str
    estimated_delivery_date: date | None
    estimated_delivery_end_date: date | None
    processing_days: int
    shipping_days: int | None
    message: str


def add_working_days(start: date, days: int, weekdays: list[int], holidays: set[date]) -> date:
    current = start
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() in weekdays and current not in holidays:
            remaining -= 1
    return current


async def estimate_delivery(
    session: AsyncSession, pincode: str, product_ids: list, speed: str = "standard", *,
    today: date | None = None,
) -> DeliveryEstimate:
    code = pincode.strip()
    pin = (await session.execute(select(Pincode).where(Pincode.pincode == code))).scalar_one_or_none()
    if not pin or not pin.is_serviceable:
        return DeliveryEstimate(False, code, pin.city if pin else None, pin.state if pin else None,
                                speed, None, None, 0, None, "Delivery is not available for this PIN code.")

    products = list((await session.execute(select(Product).where(Product.id.in_(product_ids), Product.is_active.is_(True)))).scalars().all()) if product_ids else []
    if len(products) != len(set(product_ids)):
        return DeliveryEstimate(False, code, pin.city, pin.state, speed, None, None, 0, None,
                                "One or more products are unavailable.")
    if any(product.stock_qty <= 0 for product in products):
        return DeliveryEstimate(False, code, pin.city, pin.state, speed, None, None, 0, None,
                                "One or more products are currently out of stock.")

    match = or_(ShippingRule.pincode == code, ShippingRule.city.ilike(pin.city),
                ShippingRule.state.ilike(pin.state), ShippingRule.shipping_zone.ilike(pin.shipping_zone or ""),
                (ShippingRule.pincode.is_(None) & ShippingRule.city.is_(None) & ShippingRule.state.is_(None) & ShippingRule.shipping_zone.is_(None)))
    rules = list((await session.execute(select(ShippingRule).where(ShippingRule.is_active.is_(True), match))).scalars().all())
    def priority(rule: ShippingRule) -> int:
        return 4 if rule.pincode else 3 if rule.city else 2 if rule.state else 1 if rule.shipping_zone else 0
    rules.sort(key=priority, reverse=True)
    rule = rules[0] if rules else None

    # Existing per-PIN eta_hours remains an admin-configurable fallback until a
    # destination-specific shipping rule is added.
    default_transit_days = max(1, (pin.eta_hours or 120) // 24)
    shipping_days = rule.standard_days if rule else default_transit_days
    if speed == "express":
        if not rule or rule.express_days is None:
            return DeliveryEstimate(False, code, pin.city, pin.state, speed, None, None, 0, None,
                                    "Express delivery is not configured for this PIN code.")
        shipping_days = rule.express_days
    weekdays = rule.working_weekdays if rule else [0, 1, 2, 3, 4, 5]
    holidays = {date.fromisoformat(value) for value in (rule.holidays if rule else [])}
    processing_days = max((product.processing_days for product in products), default=0)
    start = today or datetime.now(IST).date()
    processing_complete = add_working_days(start, processing_days, weekdays, holidays)
    earliest = add_working_days(processing_complete, shipping_days, weekdays, holidays)
    latest = add_working_days(earliest, 1, weekdays, holidays)
    return DeliveryEstimate(True, code, pin.city, pin.state, speed, earliest, latest,
                            processing_days, shipping_days, "Delivery available.")
