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
    stock_qty: int
    is_active: bool
    stock_warning: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CartOut(BaseModel):
    id: uuid.UUID
    items: list[CartItemOut]
    subtotal_paise: int
    item_count: int


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
    line_total: float
    available_stock: int
    is_valid: bool
    available: bool
    issues: list[str] = Field(default_factory=list)
    message: str | None = None
    name: str | None = None
    variant_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CartValidateOut(BaseModel):
    valid: bool
    items: list[CartItemValidateOut] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    subtotal: float

    model_config = ConfigDict(from_attributes=True)

