import uuid
from datetime import date
from pydantic import BaseModel, Field


class DeliveryCheckOut(BaseModel):
    pincode: str
    serviceable: bool
    city: str | None = None
    state: str | None = None
    delivery_charge: float = 0.0
    free_delivery_above: float = 0.0
    min_order: float = 0.0
    estimated_delivery: str | None = None
    cod_available: bool = False
    message: str | None = None
    # Paise fields for backward compatibility
    delivery_fee_paise: int | None = None
    free_delivery_above_paise: int | None = None
    min_order_paise: int | None = None
    eta_hours: int | None = None
    estimated_delivery_date: date | None = None
    estimated_delivery_end_date: date | None = None
    delivery_speed: str | None = None


class ProductDeliveryCheckOut(BaseModel):
    product_id: uuid.UUID
    slug: str
    pincode: str
    deliverable: bool
    reason: str | None = None
    estimated_delivery_date: date | None = None
    estimated_delivery_end_date: date | None = None


class ProductDeliveryConfigIn(BaseModel):
    mode: str = Field(..., pattern="^(all|selected)$")
    pincodes: list[str] = Field(default_factory=list)


class ProductDeliveryConfigOut(BaseModel):
    product_id: uuid.UUID
    delivery_mode: str
    pincodes: list[str]


class DeliveryEstimateIn(BaseModel):
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    delivery_speed: str = Field(default="standard", pattern="^(standard|express)$")


class DeliveryEstimateOut(BaseModel):
    serviceable: bool
    pincode: str
    city: str | None
    state: str | None
    delivery_speed: str
    estimated_delivery_date: date | None
    estimated_delivery_end_date: date | None
    processing_days: int
    shipping_days: int | None
    message: str

