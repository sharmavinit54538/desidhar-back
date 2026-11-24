import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RefundCreateIn(BaseModel):
    order_item_id: uuid.UUID | None = None
    amount_paise: int = Field(..., gt=0)
    reason: str = Field(..., pattern="^(cancelled|damaged|wrong_item|quality|late|other)$")
    restock: bool = False
    notes: str | None = None
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    expected_version: int = Field(..., ge=1)
    reference: str | None = Field(default=None, max_length=100)


class RefundOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    order_item_id: uuid.UUID | None
    amount_paise: int
    reason: str
    notes: str | None
    restock: bool
    issued_by: uuid.UUID | None
    issued_at: datetime
    created_at: datetime
    status: str
    provider_refund_id: str | None
    failure_reason: str | None
    completed_at: datetime | None
    reference: str | None

    model_config = ConfigDict(from_attributes=True)

