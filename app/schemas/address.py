import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class AddressBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., pattern=r"^[6-9][0-9]{9}$")
    line1: str = Field(..., min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    landmark: str | None = Field(default=None, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    pincode: str = Field(..., pattern=r"^[1-9][0-9]{5}$")
    is_default: bool = False

    @field_validator("full_name", "phone", "line1", "line2", "landmark", "city", "state", "pincode", mode="before")
    @classmethod
    def strip_str(cls, v):
        return v.strip() if isinstance(v, str) else v


class AddressCreate(AddressBase):
    pass


class AddressUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^[6-9][0-9]{9}$")
    line1: str | None = Field(default=None, min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    landmark: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    pincode: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")
    is_default: bool | None = None

    @field_validator("full_name", "phone", "line1", "line2", "landmark", "city", "state", "pincode", mode="before")
    @classmethod
    def strip_opt_str(cls, v):
        return v.strip() if isinstance(v, str) else v


class AddressOut(AddressBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
