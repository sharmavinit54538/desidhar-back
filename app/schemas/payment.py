import uuid
from pydantic import BaseModel, Field


class PaymentInitiateOut(BaseModel):
    order_id: uuid.UUID
    order_number: str
    provider_order_id: str
    amount_paise: int
    currency: str = "INR"


class PaymentVerifyIn(BaseModel):
    provider_order_id: str | None = Field(default=None, alias="razorpay_order_id")
    provider_payment_id: str | None = Field(default=None, alias="razorpay_payment_id")
    signature: str | None = Field(default=None, alias="razorpay_signature")

    def get_provider_order_id(self) -> str:
        return self.provider_order_id or self.razorpay_order_id or ""

    def get_provider_payment_id(self) -> str:
        return self.provider_payment_id or self.razorpay_payment_id or ""

    def get_signature(self) -> str:
        return self.signature or self.razorpay_signature or ""

