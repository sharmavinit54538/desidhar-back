import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class PincodeBase(BaseModel):
    pincode: str = Field(..., pattern=r"^[1-9][0-9]{5}$")
    area_name: str = Field(..., min_length=1, max_length=200)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    is_serviceable: bool = True
    delivery_fee_paise: int = Field(default=0, ge=0)
    free_delivery_above_paise: int | None = Field(default=None, ge=0)
    min_order_paise: int = Field(default=0, ge=0)
    cod_available: bool = False
    eta_hours: int | None = Field(default=None, ge=0)

    @field_validator("pincode", "area_name", "city", "state", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class PincodeCreate(PincodeBase):
    pass


class PincodeUpdate(BaseModel):
    pincode: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")
    area_name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    is_serviceable: bool | None = None
    delivery_fee_paise: int | None = Field(default=None, ge=0)
    free_delivery_above_paise: int | None = Field(default=None, ge=0)
    min_order_paise: int | None = Field(default=None, ge=0)
    cod_available: bool | None = None
    eta_hours: int | None = Field(default=None, ge=0)

    @field_validator("pincode", "area_name", "city", "state", mode="before")
    @classmethod
    def strip_opt_str(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class PincodeServiceableUpdate(BaseModel):
    is_serviceable: bool


class PincodeOut(BaseModel):
    id: uuid.UUID
    pincode: str
    area_name: str
    city: str
    state: str
    is_serviceable: bool
    delivery_fee_paise: int
    free_delivery_above_paise: int | None
    min_order_paise: int
    cod_available: bool
    eta_hours: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PincodeListOut(BaseModel):
    items: list[PincodeOut]
    total: int
    page: int
    page_size: int

