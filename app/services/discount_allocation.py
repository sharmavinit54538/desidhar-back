from typing import TypeVar

K = TypeVar("K")


def allocate_discount(items: list[tuple[K, int]], total_discount_paise: int) -> dict[K, int]:
    if not items or total_discount_paise <= 0:
        return {k: 0 for k, _ in items}
    subtotal = sum(v for _, v in items)
    if subtotal == 0:
        return {k: 0 for k, _ in items}
    if total_discount_paise >= subtotal:
        return {k: v for k, v in items}

    exact = [(k, (v * total_discount_paise) / subtotal, v) for k, v in items]
    allocated = {k: int(ex) for k, ex, _ in exact}
    remainders = sorted([(ex - int(ex), idx, k) for idx, (k, ex, _) in enumerate(exact)], reverse=True)
    shortfall = total_discount_paise - sum(allocated.values())
    for i in range(shortfall):
        allocated[remainders[i][2]] += 1
    return allocated
