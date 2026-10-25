import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Self


class ImageIn(BaseModel):
    url: str = Field(..., min_length=1, max_length=500)
    sort_order: int = Field(default=0)


class ImageOut(BaseModel):
    id: uuid.UUID
    url: str
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ProductCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=200)
    description: str | None = None
    price_paise: int = Field(..., ge=0)
    mrp_paise: int = Field(..., ge=0)
    unit: str
    pack_size: Decimal = Field(..., gt=0)
    stock_qty: int = Field(default=0, ge=0)
    shelf_life_days: int | None = Field(default=None, ge=1)
    is_veg: bool = True
    is_active: bool = True
    images: list[ImageIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def price_lte_mrp(self) -> Self:
        if self.price_paise > self.mrp_paise:
            raise ValueError("price_paise must not exceed mrp_paise")
        return self


class ProductUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    price_paise: int | None = Field(default=None, ge=0)
    mrp_paise: int | None = Field(default=None, ge=0)
    unit: str | None = None
    pack_size: Decimal | None = Field(default=None, gt=0)
    stock_qty: int | None = Field(default=None, ge=0)
    shelf_life_days: int | None = Field(default=None, ge=1)
    is_veg: bool | None = None
    is_active: bool | None = None
    images: list[ImageIn] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class CategoryBrief(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class ProductOut(BaseModel):
    id: uuid.UUID
    category: CategoryBrief
    name: str
    slug: str
    description: str | None
    price_paise: int
    mrp_paise: int
    unit: str
    pack_size: Decimal
    stock_qty: int
    shelf_life_days: int | None
    is_veg: bool
    is_active: bool
    images: list[ImageOut]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    pincode_serviceable: bool | None = None

