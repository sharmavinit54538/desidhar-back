import uuid
from decimal import Decimal
from typing import Optional, Dict, Any
from pydantic import BaseModel


class PaymentOrderInitResponse(BaseModel):
    order_id: uuid.UUID
    order_number: str
    amount: Decimal
    currency: str
    gateway: str
    gateway_order_id: str
    gateway_public_key: str


class RazorpayVerificationRequest(BaseModel):
    order_id: uuid.UUID
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class StripeVerificationRequest(BaseModel):
    order_id: uuid.UUID
    payment_intent_id: str
