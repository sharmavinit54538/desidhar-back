from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
import uuid


class DeliveryCashCollectionIn(BaseModel):
    expected_order_version: int = Field(ge=1)
    expected_assignment_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    amount_paise: int = Field(gt=0)
    method: str = Field(pattern="^cash$")


class DeliveryOTPVerifyIn(BaseModel):
    otp: str = Field(pattern=r"^\d{6}$")


class CashSettlementCreateIn(BaseModel):
    note: str | None = Field(default=None, max_length=255)


class CashSettlementRejectIn(BaseModel):
    note: str = Field(min_length=2, max_length=255)


class CashSettlementReconcileIn(BaseModel):
    verified_amount_paise: int = Field(ge=0)
    deposit_reference: str = Field(min_length=2, max_length=100)
    note: str | None = Field(default=None, max_length=255)


class CashSettlementOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    expected_amount_paise: int
    verified_amount_paise: int | None
    status: str
    submission_note: str | None
    deposit_reference: str | None
    review_note: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)
