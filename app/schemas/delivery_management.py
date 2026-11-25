import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.order import OrderItemOut


class DeliveryPartnerCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(pattern=r"^[6-9][0-9]{9}$")
    email: str | None = Field(default=None, max_length=255)
    employee_id: str = Field(min_length=2, max_length=50)
    service_area: str | None = Field(default=None, max_length=150)
    service_pincodes: list[str] = Field(default_factory=list, max_length=500)
    vehicle_type: str | None = Field(default=None, max_length=50)
    vehicle_registration: str | None = Field(default=None, max_length=30)
    max_active_deliveries: int = Field(default=10, ge=1, le=100)


class DeliveryPartnerOut(BaseModel):
    user_id: uuid.UUID
    employee_id: str
    full_name: str | None
    phone: str | None
    email: str | None
    is_active: bool
    service_area: str | None
    service_pincodes: list[str]
    vehicle_type: str | None
    vehicle_registration: str | None
    max_active_deliveries: int
    availability: str
    active_assignments: int = 0
    completed_deliveries: int = 0


class DeliveryAssignmentIn(BaseModel):
    partner_id: uuid.UUID


class DeliveryActionIn(BaseModel):
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, min_length=2, max_length=255)


class DeliveryAssignmentOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    partner_id: uuid.UUID
    status: str
    version: int
    assigned_at: datetime
    accepted_at: datetime | None = None
    picked_up_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    order_number: str | None = None
    fulfillment_status: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DeliveryOrderOut(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    payment_method: str
    payment_status: str
    shipping_name: str
    shipping_phone: str
    shipping_line1: str
    shipping_line2: str | None
    shipping_landmark: str | None
    shipping_city: str
    shipping_state: str
    shipping_pincode: str
    notes: str | None
    total_paise: int
    amount_paid_paise: int
    outstanding_amount_paise: int
    created_at: datetime
    items: list[OrderItemOut]
    assignment: DeliveryAssignmentOut

    model_config = ConfigDict(from_attributes=True)
