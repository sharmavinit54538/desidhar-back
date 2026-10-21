import uuid
from decimal import Decimal
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.order import OrderStatus, PaymentStatus


class ShippingAddress(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    phone: str = Field(..., min_length=10, max_length=20)
    street: str = Field(..., min_length=5, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    postal_code: str = Field(..., min_length=4, max_length=20)
    country: str = Field(default="India", max_length=100)


class OrderCreate(BaseModel):
    shipping_address: ShippingAddress
    payment_gateway: str = Field(default="RAZORPAY", description="Payment Gateway: RAZORPAY or STRIPE")


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    product_id: Optional[uuid.UUID]
    product_name_snapshot: str
    unit_price_snapshot: Decimal
    sku_snapshot: str
    quantity: int
    subtotal: Decimal

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str
    customer_id: uuid.UUID
    total_amount: Decimal
    discount_amount: Decimal
    final_payable: Decimal
    order_status: OrderStatus
    payment_status: PaymentStatus
    shipping_address: Dict[str, Any]
    payment_gateway: Optional[str]
    gateway_order_id: Optional[str]
    items: List[OrderItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderStatusUpdate(BaseModel):
    order_status: OrderStatus


class OrderRefundRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)
