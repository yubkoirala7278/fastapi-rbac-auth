import uuid

from fastapi import APIRouter, Depends

from app.common.pagination import PaginationParams, pagination_params
from app.common.response import ApiResponse, PaginatedResponse
from app.dependencies import DbSession
from app.modules.auth.controller import CurrentUser
from app.modules.auth.models import User
from app.modules.rbac.controller import RBACController, require_permission
from app.modules.rbac.dtos import (
    PermissionCreateRequest,
    PermissionResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleSummaryResponse,
    RoleUpdateRequest,
    SyncPermissionsRequest,
    SyncRolesRequest,
    UserRolesResponse,
)

router = APIRouter()


# --- Permissions --------------------------------------------------------------

@router.post(
    "/permissions",
    response_model=ApiResponse[PermissionResponse],
    dependencies=[Depends(require_permission("permission:create_permission"))],
)
async def create_permission(payload: PermissionCreateRequest, db: DbSession):
    return await RBACController(db).create_permission(payload)


@router.get(
    "/permissions",
    response_model=PaginatedResponse[PermissionResponse],
    dependencies=[Depends(require_permission("permission:view_permission"))],
)
async def list_permissions(db: DbSession, params: PaginationParams = Depends(pagination_params)):
    return await RBACController(db).list_permissions(params)


@router.delete(
    "/permissions/{permission_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("permission:delete_permission"))],
)
async def delete_permission(permission_id: uuid.UUID, db: DbSession):
    return await RBACController(db).delete_permission(permission_id)


# --- Roles --------------------------------------------------------------------

@router.post(
    "/roles",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(require_permission("role:create_role"))],
)
async def create_role(payload: RoleCreateRequest, db: DbSession):
    return await RBACController(db).create_role(payload)


@router.get(
    "/roles",
    response_model=PaginatedResponse[RoleSummaryResponse],
    dependencies=[Depends(require_permission("role:view_role"))],
)
async def list_roles(db: DbSession, params: PaginationParams = Depends(pagination_params)):
    return await RBACController(db).list_roles(params)


@router.get(
    "/roles/{role_id}",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(require_permission("role:view_role"))],
)
async def get_role(role_id: uuid.UUID, db: DbSession):
    return await RBACController(db).get_role(role_id)


@router.patch(
    "/roles/{role_id}",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(require_permission("role:edit_role"))],
)
async def update_role(role_id: uuid.UUID, payload: RoleUpdateRequest, db: DbSession):
    return await RBACController(db).update_role(role_id, payload)


@router.delete(
    "/roles/{role_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("role:delete_role"))],
)
async def delete_role(role_id: uuid.UUID, db: DbSession):
    return await RBACController(db).delete_role(role_id)


# --- Role <-> Permission assignment --------------------------------------------

@router.put(
    "/roles/{role_id}/permissions",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(require_permission("role:edit_role"))],
    summary="Set the role's permissions",
    description=(
        "Replaces the role's permissions with exactly `permission_ids`: IDs not yet "
        "assigned are added, assigned IDs missing from the list are removed. "
        "Send an empty list to remove all permissions."
    ),
)
async def sync_role_permissions(role_id: uuid.UUID, payload: SyncPermissionsRequest, db: DbSession):
    return await RBACController(db).sync_role_permissions(role_id, payload)


# --- User <-> Role assignment ----------------------------------------------

@router.get(
    "/users/{user_id}/roles",
    response_model=ApiResponse[UserRolesResponse],
    dependencies=[Depends(require_permission("user:view_user"))],
)
async def get_user_roles(user_id: uuid.UUID, db: DbSession):
    return await RBACController(db).get_user_roles(user_id)


@router.put(
    "/users/{user_id}/roles",
    response_model=ApiResponse[UserRolesResponse],
    dependencies=[Depends(require_permission("user:edit_user"))],
    summary="Set the user's roles",
    description=(
        "Replaces the user's roles with exactly `role_ids`: IDs not yet assigned "
        "are added, assigned IDs missing from the list are removed. Send an empty "
        "list to remove all roles. You cannot change your own roles."
    ),
)
async def sync_user_roles(
    user_id: uuid.UUID,
    payload: SyncRolesRequest,
    db: DbSession,
    current_user: User = CurrentUser,
):
    return await RBACController(db).sync_user_roles(user_id, payload, current_user)
