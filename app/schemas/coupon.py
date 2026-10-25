import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class CouponCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    description: str | None = None
    type: str = Field(..., pattern="^(percent|flat)$")
    value: int = Field(..., gt=0)
    max_discount_paise: int | None = Field(default=None, ge=0)
    min_order_paise: int = Field(default=0, ge=0)
    starts_at: datetime
    ends_at: datetime
    usage_limit_total: int | None = Field(default=None, gt=0)
    usage_limit_per_user: int | None = Field(default=None, gt=0)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def upper_code(cls, v: str) -> str:
        return v.strip().upper()


class CouponUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = None
    type: str | None = Field(default=None, pattern="^(percent|flat)$")
    value: int | None = Field(default=None, gt=0)
    max_discount_paise: int | None = Field(default=None, ge=0)
    min_order_paise: int | None = Field(default=None, ge=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    usage_limit_total: int | None = Field(default=None, gt=0)
    usage_limit_per_user: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def upper_opt_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


class CouponOut(BaseModel):
    id: uuid.UUID
    code: str
    description: str | None
    type: str
    value: int
    max_discount_paise: int | None
    min_order_paise: int
    starts_at: datetime
    ends_at: datetime
    usage_limit_total: int | None
    usage_limit_per_user: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

