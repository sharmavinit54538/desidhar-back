from pydantic import BaseModel, EmailStr, Field
from pydantic import ConfigDict


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class AdminLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=12)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

    model_config = ConfigDict(json_schema_extra={"example": {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600}})


class UserResponse(BaseModel):
    id: str
    role: str
    email: str | None = None
    username: str | None = None
    is_active: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)