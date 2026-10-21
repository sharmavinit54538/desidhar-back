import uuid
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.catalog import ProductStatus


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    slug: Optional[str] = Field(None, max_length=160)
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    is_active: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    slug: Optional[str] = Field(None, max_length=160)
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    id: uuid.UUID
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductImageCreate(BaseModel):
    image_url: str = Field(..., max_length=500)
    alt_text: Optional[str] = Field(None, max_length=255)
    is_primary: bool = False
    sort_order: int = 0


class ProductImageResponse(BaseModel):
    id: uuid.UUID
    image_url: str
    alt_text: Optional[str]
    is_primary: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=260)
    description: Optional[str] = None
    base_price: Decimal = Field(..., gt=0, decimal_places=2)
    sku: str = Field(..., min_length=1, max_length=100)
    stock: int = Field(default=0, ge=0)
    status: ProductStatus = ProductStatus.DRAFT
    category_id: Optional[uuid.UUID] = None
    images: List[ProductImageCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=260)
    description: Optional[str] = None
    base_price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    sku: Optional[str] = Field(None, min_length=1, max_length=100)
    stock: Optional[int] = Field(None, ge=0)
    status: Optional[ProductStatus] = None
    category_id: Optional[uuid.UUID] = None
    images: Optional[List[ProductImageCreate]] = None


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    base_price: Decimal
    sku: str
    stock: int
    status: ProductStatus
    is_deleted: bool
    category_id: Optional[uuid.UUID]
    category: Optional[CategoryResponse] = None
    images: List[ProductImageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
