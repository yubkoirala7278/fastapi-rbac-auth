import uuid

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.rbac.dtos import RoleSummaryResponse


class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    is_active: bool
    roles: list[RoleSummaryResponse] = []

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    is_active: bool | None = None


class UserPasswordUpdateRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self):
        if self.current_password == self.new_password:
            raise ValueError("New password must differ from the current password.")
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirmation password must match.")
        return self