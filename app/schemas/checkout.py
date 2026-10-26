import uuid
from pydantic import BaseModel, Field, field_validator


class CheckoutPreviewIn(BaseModel):
    address_id: uuid.UUID
    coupon_code: str | None = None
    payment_method: str | None = Field(default=None)
    items: list[dict] = Field(default_factory=list)

    @field_validator("address_id", mode="before")
    @classmethod
    def parse_address_id(cls, v: object) -> uuid.UUID:
        if isinstance(v, uuid.UUID):
            return v
        return uuid.UUID(str(v))

    @field_validator("payment_method", mode="before")
    @classmethod
    def normalize_payment_method(cls, v: object) -> str | None:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("cod", "cash", "cash on delivery"):
                return "cod"
            if s in ("online", "upi", "card", "netbanking", "net_banking"):
                return "online"
            return s
        return None


class ItemPreviewOut(BaseModel):
    product_id: uuid.UUID
    name: str
    quantity: int
    unit_price_paise: int = 0
    unit_mrp_paise: int = 0
    line_subtotal_paise: int = 0
    discount_paise: int = 0
    tax_paise: int = 0
    line_total_paise: int = 0
    deliverable: bool = True
    deliverability_reason: str | None = None


class CheckoutPreviewOut(BaseModel):
    address_id: uuid.UUID
    pincode: str
    items: list[ItemPreviewOut] = Field(default_factory=list)
    # Rupees amounts (strictly numeric floats, never null or string)
    subtotal: float = 0.0
    delivery_fee: float = 0.0
    delivery_charge: float = 0.0
    discount: float = 0.0
    total: float = 0.0
    free_delivery_above: float = 0.0
    min_order: float = 0.0
    # Paise amounts for backwards compatibility
    subtotal_paise: int = 0
    coupon_code: str | None = None
    discount_paise: int = 0
    delivery_fee_paise: int = 0
    total_paise: int = 0
    total_tax_paise: int = 0
    cod_available: bool = False
    can_checkout: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
