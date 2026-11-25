import uuid
from decimal import Decimal
from datetime import date, datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Literal


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
    delivery_speed: str = Field(default="standard", pattern="^(standard|express)$")

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
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class ShipmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    courier_name: str = Field(min_length=2, max_length=100)
    tracking_number: str | None = Field(default=None, max_length=100)
    tracking_url: str | None = Field(default=None, max_length=1000)
    shipment_reference: str | None = Field(default=None, max_length=100)
    shipped_at: datetime | None = None
    estimated_delivery_date: date | None = None
    estimated_delivery_end_date: date | None = None
    revised_delivery_date: date | None = None
    actual_delivery_date: datetime | None = None
    delivery_status: str | None = None
    delivery_speed: str = "standard"
    delay_reason: str | None = None
    estimated_delivery_at: datetime | None = None

    @field_validator("tracking_url")
    @classmethod
    def safe_tracking_url(cls, value):
        if value:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Tracking URL must be an HTTP(S) URL without credentials")
        return value

    @field_validator("shipped_at", "estimated_delivery_at")
    @classmethod
    def aware_date(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return value


class OrderActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)
    reason: str | None = Field(default=None, min_length=2, max_length=255)
    customer_visible_message: str | None = Field(default=None, max_length=500)
    internal_admin_note: str | None = Field(default=None, max_length=1000)
    shipment: ShipmentIn | None = None
    inspection_passed: bool = False
    restock: bool = False


class CustomerReturnIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    reason: str = Field(min_length=2, max_length=255)


class CODCollectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    amount_paise: int = Field(gt=0)
    collection_method: Literal["cash", "upi", "card", "bank_transfer"]
    reference: str = Field(min_length=2, max_length=100)
    collected_at: datetime


class RefundProcessIn(BaseModel):
    reference: str | None = Field(default=None, min_length=2, max_length=100)


class OrderStatusUpdateIn(OrderActionIn):
    expected_version: int = Field(ge=1)
    status: str
    note: str | None = Field(default=None, max_length=255)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: object) -> str:
        if isinstance(v, str):
            s = v.strip().lower()
            return s
        return str(v)


class DeliveryDetailsUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    estimated_delivery_date: date | None = None
    estimated_delivery_end_date: date | None = None
    revised_delivery_date: date | None = None
    delay_reason: str | None = Field(default=None, min_length=2, max_length=500)
    courier_name: str | None = Field(default=None, min_length=2, max_length=100)
    tracking_number: str | None = Field(default=None, max_length=150)
    tracking_url: str | None = Field(default=None, max_length=2048)

    @field_validator("tracking_url")
    @classmethod
    def valid_tracking_url(cls, value):
        if value:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Tracking URL must be an HTTP(S) URL without credentials")
        return value


class OrderItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name_snapshot: str
    pack_size_snapshot: Decimal
    unit_snapshot: str
    quantity: int
    unit_price_paise: int
    unit_mrp_paise: int
    gst_rate_percent: Decimal
    discount_paise: int
    tax_paise: int
    line_total_paise: int
    image_url: str | None = None
    product_slug: str | None = None
    sku: str | None = None
    variant_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OrderStatusHistoryOut(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime
    customer_visible_message: str | None = None
    event_source: str | None = None

    @model_validator(mode="before")
    @classmethod
    def redact_private_note(cls, value):
        if not isinstance(value, dict):
            return {"id": value.id, "from_status": value.from_status, "to_status": value.to_status,
                    "note": getattr(value, "customer_visible_message", None), "created_at": value.created_at,
                    "customer_visible_message": getattr(value, "customer_visible_message", None),
                    "event_source": getattr(value, "event_source", None)}
        return value

    model_config = ConfigDict(from_attributes=True)


class AdminOrderStatusHistoryOut(OrderStatusHistoryOut):
    changed_by: uuid.UUID | None = None
    actor_type: str | None = None
    reason: str | None = None
    internal_admin_note: str | None = None
    idempotency_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def redact_private_note(cls, value):
        return value


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    courier_name: str
    tracking_number: str | None = None
    tracking_url: str | None = None
    shipment_reference: str | None = None
    shipment_status: str
    shipped_at: datetime | None = None
    estimated_delivery_at: datetime | None = None
    delivered_at: datetime | None = None
    delivery_failure_reason: str | None = None


class OrderPaymentOut(BaseModel):
    id: uuid.UUID
    method: str
    provider: str | None
    provider_order_id: str | None
    provider_payment_id: str | None = None
    status: str
    amount_paise: int
    paid_at: datetime | None
    collection_method: str | None = None
    collection_reference: str | None = None

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
    updated_at: datetime | None = None
    version: int = 1
    fulfillment_status: str | None = None
    packed_at: datetime | None = None
    shipped_at: datetime | None = None
    out_for_delivery_at: datetime | None = None
    amount_paid_paise: int = 0
    outstanding_amount_paise: int = 0
    customer_email: str | None = None
    billing_address: dict | None = None
    invoice_available: bool = False
    invoice_number: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    shipment: ShipmentOut | None = None
    items: list[OrderItemOut] = Field(default_factory=list)
    history: list[OrderStatusHistoryOut] = Field(default_factory=list)
    payments: list[OrderPaymentOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AdminOrderOut(OrderOut):
    history: list[AdminOrderStatusHistoryOut] = Field(default_factory=list)


class PlaceOrderResponse(BaseModel):
    order: OrderOut
    payment_url: str | None = None


class OrderTrackingOut(BaseModel):
    order_id: uuid.UUID
    order_number: str
    status: str
    delivery_status: str
    order_date: datetime
    estimated_delivery_date: date | None = None
    estimated_delivery_end_date: date | None = None
    revised_delivery_date: date | None = None
    actual_delivery_date: datetime | None = None
    delay_reason: str | None = None
    shipping_pincode: str
    courier_name: str | None = None
    tracking_id: str | None = None
    tracking_url: str | None = None
    timeline: list[OrderStatusHistoryOut] = Field(default_factory=list)


class OrderListOut(BaseModel):
    items: list[OrderOut]
    total: int
    page: int
    page_size: int


class AdminOrderListOut(OrderListOut):
    items: list[AdminOrderOut]


class OrderSummaryOut(BaseModel):
    total_orders: int
    new_orders: int
    confirmed_orders: int
    pending_packing: int
    packed_orders: int
    shipped_orders: int
    out_for_delivery: int
    delivered_orders: int
    cancelled_orders: int
    failed_deliveries: int
    return_requests: int
    pending_refunds: int
    pending_cod_collection: int
    pending_cod_amount_paise: int

