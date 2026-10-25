from decimal import Decimal


def compute_tax_paise(line_after_discount_paise: int, gst_rate_percent: Decimal | float | int) -> int:
    rate = Decimal(str(gst_rate_percent))
    if line_after_discount_paise <= 0 or rate <= 0:
        return 0
    tax = (Decimal(line_after_discount_paise) * rate) / (Decimal(100) + rate)
    return int(round(tax))

