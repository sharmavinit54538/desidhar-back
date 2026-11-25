import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ShippingRuleIn(BaseModel):
    pincode: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    shipping_zone: str | None = Field(default=None, min_length=2, max_length=100)
    standard_days: int = Field(default=5, ge=0, le=60)
    express_days: int | None = Field(default=None, ge=0, le=30)
    working_weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5], min_length=1, max_length=7)
    holidays: list[str] = Field(default_factory=list, max_length=366)
    is_active: bool = True

    @field_validator("working_weekdays")
    @classmethod
    def valid_weekdays(cls, days):
        if len(set(days)) != len(days) or any(day < 0 or day > 6 for day in days):
            raise ValueError("working_weekdays must contain unique values from 0 to 6 (Monday=0)")
        return days

    @field_validator("holidays")
    @classmethod
    def valid_holidays(cls, days):
        from datetime import date
        normalized = sorted({date.fromisoformat(day).isoformat() for day in days})
        return normalized

class ShippingRuleOut(ShippingRuleIn):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
