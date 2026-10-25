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

