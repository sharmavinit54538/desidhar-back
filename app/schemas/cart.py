import uuid
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class CartItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=100)


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=1, le=100)


class CartItemResponse(BaseModel):
    id: Optional[uuid.UUID] = None
    product_id: uuid.UUID
    product_name: str
    sku: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    in_stock: bool
    stock_available: int
    image_url: Optional[str] = None


class CartResponse(BaseModel):
    id: Optional[uuid.UUID] = None
    items: List[CartItemResponse] = Field(default_factory=list)
    total_items: int = 0
    total_amount: Decimal = Decimal("0.00")
    currency: str = "INR"


class MergeCartRequest(BaseModel):
    guest_session_id: str = Field(..., min_length=1)
