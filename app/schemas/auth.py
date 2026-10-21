import uuid
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.user import UserRole, UserStatus


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters long")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    guest_session_id: Optional[str] = Field(None, description="Optional guest session id to auto-merge cart")


class StaffCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole
    permissions: List[str] = Field(
        default_factory=list,
        description="List of granular permissions, e.g. ['product:write', 'order:refund', 'inventory:update']",
    )

    @field_validator("role")
    @classmethod
    def validate_staff_role(cls, v: UserRole) -> UserRole:
        if v not in (UserRole.STORE_MANAGER, UserRole.SUPPORT_STAFF):
            raise ValueError("Staff role must be either STORE_MANAGER or SUPPORT_STAFF")
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
    guest_session_id: Optional[str] = Field(None, description="Optional guest cart session id for automatic merging")


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    role: UserRole
    status: UserStatus
    permissions: List[str]
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes in seconds
    user: UserResponse


class SessionResponse(BaseModel):
    id: uuid.UUID
    ip_address: Optional[str]
    user_agent: Optional[str]
    expires_at: datetime
    is_revoked: bool
    created_at: datetime

    model_config = {"from_attributes": True}
