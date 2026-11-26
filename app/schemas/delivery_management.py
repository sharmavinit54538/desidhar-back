import uuid
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    availability: Literal["available", "offline"] = "offline"

    @field_validator("service_pincodes", mode="before")
    @classmethod
    def normalize_pincodes(cls, v):
        if v is None:
            return []
        return list(dict.fromkeys(str(pin).strip() for pin in v if str(pin).strip()))


class DeliveryPartnerUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^[6-9][0-9]{9}$")
    email: str | None = Field(default=None, max_length=255)
    employee_id: str | None = Field(default=None, min_length=2, max_length=50)
    service_area: str | None = Field(default=None, max_length=150)
    service_pincodes: list[str] | None = Field(default=None, max_length=500)
    vehicle_type: str | None = Field(default=None, max_length=50)
    vehicle_registration: str | None = Field(default=None, max_length=30)
    max_active_deliveries: int | None = Field(default=None, ge=1, le=100)
    availability: Literal["available", "offline"] | None = None
    is_active: bool | None = None
    is_suspended: bool | None = None

    @field_validator("service_pincodes", mode="before")
    @classmethod
    def normalize_pincodes(cls, v):
        if v is None:
            return None
        return list(dict.fromkeys(str(pin).strip() for pin in v if str(pin).strip()))


class DeliveryPartnerOut(BaseModel):
    user_id: uuid.UUID
    employee_id: str
    full_name: str | None
    phone: str | None
    email: str | None
    is_active: bool
    is_suspended: bool = False
    deleted_at: datetime | None = None
    service_area: str | None
    service_pincodes: list[str]
    vehicle_type: str | None
    vehicle_registration: str | None
    max_active_deliveries: int
    availability: str
    active_assignments: int = 0
    completed_deliveries: int = 0
    remaining_capacity: int = 0


class DeliveryAssignmentIn(BaseModel):
    partner_id: uuid.UUID


class DeliveryActionIn(BaseModel):
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, min_length=2, max_length=255)


class DeliveryCompleteIn(BaseModel):
    expected_order_version: int = Field(ge=1)
    expected_assignment_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    otp: str = Field(pattern=r"^\d{6}$")
    cash_collected: bool = False
    collected_amount_paise: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=255)


class DeliveryAssignmentHistoryOut(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    order_id: uuid.UUID
    actor_id: uuid.UUID
    actor_name: str | None = None
    from_status: str | None = None
    to_status: str
    note: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    delivery_status: str | None = None
    partner_name: str | None = None
    partner_phone: str | None = None
    partner_employee_id: str | None = None
    partner_service_area: str | None = None
    partner_availability: str | None = None
    assigned_by_name: str | None = None
    expected_delivery_date: date | None = None
    estimated_delivery_end_date: date | None = None
    shipping_pincode: str | None = None
    shipping_name: str | None = None
    history: list[DeliveryAssignmentHistoryOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DeliveryPartnerDetailOut(DeliveryPartnerOut):
    assigned_orders: list[DeliveryAssignmentOut] = Field(default_factory=list)
    completed_orders: list[DeliveryAssignmentOut] = Field(default_factory=list)
    assignment_history: list[DeliveryAssignmentHistoryOut] = Field(default_factory=list)


class EligibleDeliveryPartnerOut(BaseModel):
    user_id: uuid.UUID
    employee_id: str
    full_name: str | None
    phone: str | None
    email: str | None
    is_active: bool
    is_suspended: bool = False
    service_area: str | None
    service_pincodes: list[str]
    vehicle_type: str | None
    vehicle_registration: str | None
    max_active_deliveries: int
    availability: str
    active_assignments: int
    completed_deliveries: int
    remaining_capacity: int
    is_eligible: bool
    ineligibility_reason: str | None = None


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
    version: int
    delivery_status: str | None = None
    estimated_delivery_date: date | None = None
    estimated_delivery_end_date: date | None = None
    revised_delivery_date: date | None = None
    actual_delivery_date: datetime | None = None
    created_at: datetime
    items: list[OrderItemOut]
    assignment: DeliveryAssignmentOut

    model_config = ConfigDict(from_attributes=True)
