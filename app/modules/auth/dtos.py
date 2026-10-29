import uuid

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.rbac.dtos import RoleSummaryResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    is_active: bool
    roles: list[RoleSummaryResponse] = []

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None

    @model_validator(mode="after")
    def require_profile_field(self):
        if self.name is None and self.email is None:
            raise ValueError("At least one profile field must be provided.")
        return self