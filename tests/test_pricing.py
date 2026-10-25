from decimal import Decimal
from app.services.discount_allocation import allocate_discount
from app.services.tax_service import compute_tax_paise


def test_discount_allocation():
    items = [("item1", 100), ("item2", 200), ("item3", 300)]
    allocated = allocate_discount(items, 100)
    assert sum(allocated.values()) == 100
    assert allocated["item1"] == 17
    assert allocated["item2"] == 33
    assert allocated["item3"] == 50


def test_discount_allocation_edge_cases():
    assert allocate_discount([], 50) == {}
    assert allocate_discount([("a", 100)], 0) == {"a": 0}
    assert allocate_discount([("a", 100)], 200) == {"a": 100}


def test_tax_computation():
    assert compute_tax_paise(10500, Decimal("5.00")) == 500
    assert compute_tax_paise(11800, Decimal("18.00")) == 1800
    assert compute_tax_paise(10000, Decimal("0.00")) == 0

