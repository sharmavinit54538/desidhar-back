import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

