import uuid
from pydantic import BaseModel, Field


class DeliveryCheckOut(BaseModel):
    pincode: str
    serviceable: bool
    city: str | None = None
    state: str | None = None
    delivery_fee_paise: int | None = None
    free_delivery_above_paise: int | None = None
    min_order_paise: int | None = None
    cod_available: bool | None = None
    eta_hours: int | None = None
    message: str | None = None


class ProductDeliveryCheckOut(BaseModel):
    product_id: uuid.UUID
    slug: str
    pincode: str
    deliverable: bool
    reason: str | None = None


class ProductDeliveryConfigIn(BaseModel):
    mode: str = Field(..., pattern="^(all|selected)$")
    pincodes: list[str] = Field(default_factory=list)


class ProductDeliveryConfigOut(BaseModel):
    product_id: uuid.UUID
    delivery_mode: str
    pincodes: list[str]

