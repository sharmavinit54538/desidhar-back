import uuid
from pydantic import BaseModel, Field


class CheckoutPreviewIn(BaseModel):
    address_id: uuid.UUID
    coupon_code: str | None = None
    payment_method: str | None = Field(default=None, pattern="^(cod|online)$")


class ItemPreviewOut(BaseModel):
    product_id: uuid.UUID
    name: str
    quantity: int
    unit_price_paise: int
    unit_mrp_paise: int
    line_subtotal_paise: int
    discount_paise: int
    tax_paise: int
    line_total_paise: int
    deliverable: bool
    deliverability_reason: str | None = None


class CheckoutPreviewOut(BaseModel):
    address_id: uuid.UUID
    pincode: str
    items: list[ItemPreviewOut]
    subtotal_paise: int
    coupon_code: str | None = None
    discount_paise: int = 0
    delivery_fee_paise: int = 0
    total_paise: int
    total_tax_paise: int
    cod_available: bool
    can_checkout: bool
    blocking_reasons: list[str] = Field(default_factory=list)

