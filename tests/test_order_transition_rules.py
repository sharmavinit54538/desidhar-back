from app.models.order import OrderStatus
from app.services.order_transition import ALLOWED_TRANSITIONS, can_transition


def test_canonical_fulfillment_transitions_are_sequential():
    expected = {
        OrderStatus.placed.value: {OrderStatus.confirmed.value, OrderStatus.cancelled.value},
        OrderStatus.confirmed.value: {OrderStatus.packed.value, OrderStatus.cancelled.value},
        OrderStatus.packed.value: {OrderStatus.shipped.value, OrderStatus.cancelled.value},
        OrderStatus.shipped.value: {OrderStatus.out_for_delivery.value, OrderStatus.delivery_failed.value},
        OrderStatus.out_for_delivery.value: {OrderStatus.delivered.value, OrderStatus.delivery_failed.value},
        OrderStatus.delivered.value: {OrderStatus.return_requested.value},
        OrderStatus.cancelled.value: set(),
    }
    for current, permitted in expected.items():
        assert ALLOWED_TRANSITIONS[current] == permitted


def test_admin_cannot_skip_a_fulfillment_stage():
    ok, error = can_transition("confirmed", "shipped", is_admin=True)
    assert not ok
    assert "current='confirmed'" in error
    assert "requested='shipped'" in error
    assert "packed" in error


def test_pending_payment_is_not_a_placed_fulfillment_order():
    ok, error = can_transition("payment_pending", "placed", is_admin=True)
    assert not ok
    assert "payment_pending" in error
    assert "placed" in error
    assert "cancelled" in error


def test_terminal_fulfillment_status_cannot_move_backwards():
    ok, error = can_transition("delivered", "confirmed", is_admin=True)
    assert not ok
    assert "return_requested" in error
