import uuid
from pydantic import BaseModel


class PaymentInitiateOut(BaseModel):
    order_id: uuid.UUID
    order_number: str
    provider_order_id: str
    amount_paise: int
    currency: str = "INR"


class PaymentVerifyIn(BaseModel):
    provider_order_id: str
    provider_payment_id: str
    signature: str

