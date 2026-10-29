import uuid

from pydantic import BaseModel, Field


class PermissionResponse(BaseModel):
    id: uuid.UUID
    module: str
    action: str
    code: str

    model_config = {"from_attributes": True}


class PermissionCreateRequest(BaseModel):
    module: str = Field(min_length=1, max_length=50, examples=["user"])
    action: str = Field(min_length=1, max_length=80, examples=["create_user"])


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    permissions: list[PermissionResponse] = []

    model_config = {"from_attributes": True}


class RoleSummaryResponse(BaseModel):
    """Lightweight role shape, without the nested permission list (used in lists)."""

    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)


class SyncPermissionsRequest(BaseModel):
    """
    The complete set of permissions the role should hold. Permissions missing
    from the list are removed; an empty list removes all of them.
    """

    permission_ids: list[uuid.UUID] = Field(default_factory=list)


class SyncRolesRequest(BaseModel):
    """
    The complete set of roles the user should hold. Roles missing from the
    list are removed; an empty list removes all of them.
    """

    role_ids: list[uuid.UUID] = Field(default_factory=list)


class UserRolesResponse(BaseModel):
    user_id: uuid.UUID
    roles: list[RoleSummaryResponse]