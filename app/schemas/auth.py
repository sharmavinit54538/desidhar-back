from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic import ConfigDict


class OTPRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class OTPVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class AdminLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=12)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None

    model_config = ConfigDict(json_schema_extra={"example": {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600, "refresh_token": "eyJ..."}})


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^[6-9][0-9]{9}$")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class UserResponse(BaseModel):
    id: str
    role: str
    email: str | None = None
    full_name: str | None = None
    phone: str | None = None
    username: str | None = None
    is_active: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)
