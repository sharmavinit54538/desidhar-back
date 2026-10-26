import uuid
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class OrderItemIn(BaseModel):
    product_id: uuid.UUID
    variant_id: str | None = None
    quantity: int = Field(default=1, ge=1)

    @field_validator("product_id", mode="before")
    @classmethod
    def parse_product_id(cls, v: object) -> uuid.UUID:
        if isinstance(v, uuid.UUID):
            return v
        return uuid.UUID(str(v))


class OrderCreateIn(BaseModel):
    address_id: uuid.UUID
    payment_method: str = Field(..., pattern="^(cod|online)$")
    items: list[OrderItemIn] = Field(default_factory=list)
    coupon_code: str | None = None
    notes: str | None = None

    @field_validator("address_id", mode="before")
    @classmethod
    def parse_address_id(cls, v: object) -> uuid.UUID:
        if isinstance(v, uuid.UUID):
            return v
        return uuid.UUID(str(v))

    @field_validator("payment_method", mode="before")
    @classmethod
    def normalize_payment_method(cls, v: object) -> str:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("cod", "cash", "cash on delivery"):
                return "cod"
            if s in ("online", "upi", "card", "netbanking", "net_banking"):
                return "online"
            return s
        return str(v)



class CancelOrderIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=255)


class OrderStatusUpdateIn(BaseModel):
    status: str
    note: str | None = None


class OrderItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name_snapshot: str
    pack_size_snapshot: Decimal
    unit_snapshot: str
    quantity: int
    unit_price_paise: int
    unit_mrp_paise: int
    unit_cost_paise: int
    gst_rate_percent: Decimal
    discount_paise: int
    tax_paise: int
    line_total_paise: int

    model_config = ConfigDict(from_attributes=True)


class OrderStatusHistoryOut(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderPaymentOut(BaseModel):
    id: uuid.UUID
    method: str
    provider: str | None
    provider_order_id: str | None
    status: str
    amount_paise: int
    paid_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    payment_method: str
    payment_status: str
    shipping_name: str
    shipping_phone: str
    shipping_line1: str
    shipping_line2: str | None
    shipping_landmark: str | None
    shipping_city: str
    shipping_state: str
    shipping_pincode: str
    subtotal_paise: int
    discount_paise: int
    coupon_code: str | None
    delivery_fee_paise: int
    total_paise: int
    tax_paise: int
    notes: str | None
    placed_at: datetime | None
    confirmed_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    items: list[OrderItemOut] = Field(default_factory=list)
    history: list[OrderStatusHistoryOut] = Field(default_factory=list)
    payments: list[OrderPaymentOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class OrderListOut(BaseModel):
    items: list[OrderOut]
    total: int
    page: int
    page_size: int

