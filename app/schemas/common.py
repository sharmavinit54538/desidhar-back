from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class RFC7807ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: Optional[str] = None
    type: Optional[str] = None


class RFC7807ErrorResponse(BaseModel):
    status: int
    error_code: str
    message: str
    details: List[RFC7807ErrorDetail] = Field(default_factory=list)
    timestamp: str
    path: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int
