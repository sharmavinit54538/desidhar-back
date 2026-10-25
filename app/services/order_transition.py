from app.models.order import OrderStatus

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.payment_pending.value: {OrderStatus.placed.value, OrderStatus.cancelled.value},
    OrderStatus.placed.value: {OrderStatus.confirmed.value, OrderStatus.cancelled.value},
    OrderStatus.confirmed.value: {OrderStatus.packed.value, OrderStatus.cancelled.value},
    OrderStatus.packed.value: {OrderStatus.out_for_delivery.value, OrderStatus.cancelled.value},
    OrderStatus.out_for_delivery.value: {OrderStatus.delivered.value, OrderStatus.delivery_failed.value},
    OrderStatus.delivery_failed.value: {OrderStatus.out_for_delivery.value, OrderStatus.cancelled.value},
    OrderStatus.delivered.value: set(),
    OrderStatus.cancelled.value: set(),
}


def can_transition(current: str, target: str, is_admin: bool = False) -> tuple[bool, str | None]:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        return False, f"Cannot transition from {current} to {target}"
    if target == OrderStatus.cancelled.value and not is_admin:
        if current not in (OrderStatus.placed.value, OrderStatus.confirmed.value):
            return False, f"Customer may cancel only while placed or confirmed (current: {current})"
    return True, None
