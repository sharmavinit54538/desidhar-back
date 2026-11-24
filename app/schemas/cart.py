import uuid
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


class CartItemUpdateIn(BaseModel):
    quantity: int = Field(..., ge=0)


class CartItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    slug: str
    unit: str
    pack_size: Decimal
    unit_price_paise: int
    unit_mrp_paise: int
    quantity: int
    line_total_paise: int
    line_mrp_total_paise: int = 0
    discount_paise: int = 0
    discount_percent: float = 0.0
    stock_qty: int
    max_qty_per_order: int = 10
    is_active: bool
    stock_warning: str | None = None
    image_url: str | None = None
    category_name: str | None = None
    category_slug: str | None = None
    description: str | None = None
    is_veg: bool = True
    gst_rate_percent: float = 0.0
    variant_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CartSummaryOut(BaseModel):
    item_count: int = 0
    total_mrp_paise: int = 0
    product_discount_paise: int = 0
    coupon_discount_paise: int = 0
    coupon_code: str | None = None
    subtotal_paise: int = 0
    delivery_charge_paise: int | None = None
    delivery_charge_note: str | None = None
    packaging_charge_paise: int = 0
    tax_paise: int = 0
    total_savings_paise: int = 0
    total_paise: int = 0


class CartOut(BaseModel):
    id: uuid.UUID
    items: list[CartItemOut]
    subtotal_paise: int
    item_count: int
    summary: CartSummaryOut


class CartItemValidateIn(BaseModel):
    product_id: str
    variant_id: str | None = None
    quantity: int = Field(default=1, ge=0)


class CartValidateIn(BaseModel):
    items: list[CartItemValidateIn] = Field(default_factory=list)


class CartItemValidateOut(BaseModel):
    product_id: str
    variant_id: str | None = None
    quantity: int
    price: float
    unit_price: float
    mrp: float = 0.0
    line_total: float
    available_stock: int
    is_valid: bool
    available: bool
    issues: list[str] = Field(default_factory=list)
    message: str | None = None
    name: str | None = None
    variant_label: str | None = None
    image_url: str | None = None
    slug: str | None = None
    discount_percent: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class CartValidateOut(BaseModel):
    valid: bool
    items: list[CartItemValidateOut] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    subtotal: float

    model_config = ConfigDict(from_attributes=True)

