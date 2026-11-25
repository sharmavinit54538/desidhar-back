from app.models.order import OrderStatus

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    # Payment completion is owned by the payment callback; admin fulfillment
    # transitions must not turn an unpaid online order into a placed order.
    OrderStatus.payment_pending.value: {OrderStatus.cancelled.value},
    OrderStatus.placed.value: {OrderStatus.confirmed.value, OrderStatus.cancelled.value},
    OrderStatus.confirmed.value: {OrderStatus.packed.value, OrderStatus.cancelled.value},
    OrderStatus.packed.value: {OrderStatus.shipped.value, OrderStatus.cancelled.value},
    OrderStatus.shipped.value: {OrderStatus.out_for_delivery.value, OrderStatus.delivery_failed.value},
    OrderStatus.out_for_delivery.value: {OrderStatus.delivered.value, OrderStatus.delivery_failed.value},
    OrderStatus.delivery_failed.value: {OrderStatus.out_for_delivery.value, OrderStatus.cancelled.value},
    OrderStatus.delivered.value: {OrderStatus.return_requested.value},
    OrderStatus.cancelled.value: set(),
    OrderStatus.return_requested.value: {OrderStatus.return_approved.value, OrderStatus.return_rejected.value},
    OrderStatus.return_approved.value: {OrderStatus.return_in_transit.value},
    OrderStatus.return_rejected.value: set(),
    OrderStatus.return_in_transit.value: {OrderStatus.returned.value},
    OrderStatus.returned.value: set(),
}


def can_transition(current: str, target: str, is_admin: bool = False) -> tuple[bool, str | None]:
    if current == target:
        allowed = ", ".join(sorted(ALLOWED_TRANSITIONS.get(current, set()))) or "none"
        return False, (
            f"Invalid order status transition: current='{current}', requested='{target}'. "
            f"Reason: order is already in this status. Permitted next statuses: {allowed}."
        )
    allowed = sorted(list(ALLOWED_TRANSITIONS.get(current, set())))
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        allowed_str = ", ".join(allowed) if allowed else "none"
        return False, (
            f"Invalid order status transition: current='{current}', requested='{target}'. "
            f"Reason: transition is not permitted. Permitted next statuses: {allowed_str}."
        )
    if target == OrderStatus.cancelled.value and not is_admin:
        if current not in (OrderStatus.payment_pending.value, OrderStatus.placed.value, OrderStatus.confirmed.value):
            return False, f"Customer may cancel only while payment pending, placed, or confirmed (current: {current})"
    if target.startswith("return_") and not is_admin and target != OrderStatus.return_requested.value:
        return False, "Customers may only request a return"
    return True, None

