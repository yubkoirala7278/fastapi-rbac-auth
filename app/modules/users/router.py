import uuid

from fastapi import APIRouter, Depends

from app.common.pagination import PaginationParams, pagination_params
from app.common.response import ApiResponse, PaginatedResponse
from app.dependencies import DbSession
from app.modules.rbac.controller import require_permission
from app.modules.auth.controller import CurrentUser
from app.modules.auth.models import User
from app.modules.users.controller import UserController
from app.modules.users.dtos import (
    UserCreateRequest,
    UserPasswordUpdateRequest,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[UserResponse],
    dependencies=[Depends(require_permission("user:create_user"))],
)
async def create_user(payload: UserCreateRequest, db: DbSession):
    return await UserController(db).create_user(payload)


@router.get(
    "",
    response_model=PaginatedResponse[UserResponse],
    dependencies=[Depends(require_permission("user:view_user"))],
)
async def list_users(db: DbSession, params: PaginationParams = Depends(pagination_params)):
    return await UserController(db).list_users(params)


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
    dependencies=[Depends(require_permission("user:view_user"))],
)
async def get_user(user_id: uuid.UUID, db: DbSession):
    return await UserController(db).get_user(user_id)


@router.patch(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
    dependencies=[Depends(require_permission("user:edit_user"))],
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: DbSession,
    current_user: User = CurrentUser,
):
    return await UserController(db).update_user(user_id, payload, current_user)


@router.patch(
    "/{user_id}/password",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("user:edit_user"))],
)
async def update_user_password(user_id: uuid.UUID, payload: UserPasswordUpdateRequest, db: DbSession):
    return await UserController(db).update_password(user_id, payload)


@router.delete(
    "/{user_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("user:delete_user"))],
)
async def delete_user(
    user_id: uuid.UUID,
    db: DbSession,
    current_user: User = CurrentUser,
):
    return await UserController(db).delete_user(user_id, current_user)